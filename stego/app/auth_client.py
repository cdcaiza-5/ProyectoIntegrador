"""Cliente de AUTH (contratos 1, 2 y 3).

Tres responsabilidades, todas de solo lectura sobre material público:

* verificar el access token del usuario con la clave pública del JWKS;
* obtener y renovar el token de servicio (``client_credentials``, TTL 300 s,
  renovación a los 240 s);
* pedir la decisión de autorización a ``/internal/authorization/check``.

Cualquier fallo de AUTH (inaccesible, timeout, respuesta no parseable, token de
servicio inválido) se traduce a ``503 AUTHORIZATION_UNAVAILABLE``: es el fallo
seguro exigido por T08. Nunca se reintenta una autorización y nunca se cachea
una decisión: cada petición del cliente pide la suya.

STEGO no consulta la base de AUTH ni recibe jamás la clave privada de firma.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm
from jwt.exceptions import InvalidKeyError
from pydantic import ValidationError

from app.config import Settings
from app.errors import ApiError, ErrorCode
from app.request_ids import upstream_request_id
from app.schemas import AuthorizationDecision, ServiceTokenResponse
from app.timeutils import utcnow

logger = logging.getLogger("stego.auth")
audit = logging.getLogger("stego.audit")

ALLOWED_ALGORITHM = "RS256"
ALLOWED_KEY_TYPE = "JWT"
ACCESS_TOKEN_USE = "access"
SERVICE_TOKEN_USE = "service"
SERVICE_TOKEN_AUDIENCE = "auth-internal"
REQUIRED_CLAIMS = ("iss", "sub", "aud", "iat", "exp", "jti", "token_use")

ACTION_ANALYZE = "steganography.analyze"
ACTION_RESULTS_READ = "steganography.results.read"


@dataclass(frozen=True)
class AccessToken:
    subject: uuid.UUID
    jti: str
    expires_at: datetime
    raw: str
    claims: dict[str, Any]


def _invalid_token(message: str | None = None) -> ApiError:
    return ApiError(ErrorCode.TOKEN_INVALID, message=message)


def _decode_segment(segment: str) -> Any:
    padding = "=" * (-len(segment) % 4)
    try:
        raw = base64.urlsafe_b64decode(segment + padding)
    except (binascii.Error, ValueError) as exc:
        raise _invalid_token() from exc
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise _invalid_token() from exc


def _decode_header(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise _invalid_token()
    header = _decode_segment(parts[0])
    if not isinstance(header, dict):
        raise _invalid_token()
    if header.get("alg") != ALLOWED_ALGORITHM:
        raise _invalid_token()
    if str(header.get("typ", "")).upper() != ALLOWED_KEY_TYPE:
        raise _invalid_token()
    if "crit" in header:
        raise _invalid_token()
    kid = header.get("kid")
    if not isinstance(kid, str) or not kid:
        raise _invalid_token()
    return header


def _decode_payload(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise ApiError(ErrorCode.AUTHORIZATION_UNAVAILABLE)
    payload = _decode_segment(parts[1])
    if not isinstance(payload, dict):
        raise ApiError(ErrorCode.AUTHORIZATION_UNAVAILABLE)
    return payload


def _uuid_or_none(value: Any) -> uuid.UUID | None:
    if not isinstance(value, str):
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


class JwksVerifier:
    """Verificación del access token del usuario (contrato 1 §3)."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._client = client
        self._keys: dict[str, Any] = {}
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    async def verify(self, token: str) -> AccessToken:
        header = _decode_header(token)
        key = await self._public_key(header["kid"])
        try:
            claims = jwt.decode(
                token,
                key=key,
                algorithms=[ALLOWED_ALGORITHM],
                audience=self._settings.jwt_audience,
                issuer=self._settings.jwt_issuer,
                leeway=self._settings.stego_jwt_leeway_seconds,
                options={"require": list(REQUIRED_CLAIMS)},
            )
        except jwt.ExpiredSignatureError as exc:
            raise ApiError(ErrorCode.TOKEN_EXPIRED) from exc
        except jwt.ImmatureSignatureError as exc:
            raise ApiError(ErrorCode.TOKEN_EXPIRED) from exc
        except jwt.InvalidTokenError as exc:
            raise _invalid_token() from exc

        if claims.get("token_use") != ACCESS_TOKEN_USE:
            raise _invalid_token()
        subject = _uuid_or_none(claims.get("sub"))
        if subject is None:
            raise _invalid_token()
        jti = claims.get("jti")
        if not isinstance(jti, str) or not jti:
            raise _invalid_token()
        return AccessToken(
            subject=subject,
            jti=jti,
            expires_at=datetime.fromtimestamp(claims["exp"], tz=UTC),
            raw=token,
            claims=claims,
        )

    async def _public_key(self, kid: str) -> Any:
        async with self._lock:
            if kid in self._keys and time.monotonic() < self._expires_at:
                return self._keys[kid]
            stale = self._keys.get(kid)
            try:
                await self._fetch_keys()
            except ApiError:
                if stale is not None:
                    logger.warning(
                        "jwks_refresh_failed_using_cached_key",
                        extra={"fields": {"kid": kid}},
                    )
                    return stale
                raise
            if kid not in self._keys:
                if stale is not None:
                    return stale
                raise _invalid_token("El token no corresponde a una clave publicada.")
            return self._keys[kid]

    async def _fetch_keys(self) -> None:
        try:
            response = await self._client.get(
                self._settings.stego_auth_jwks_url,
                timeout=self._settings.jwks_timeout_seconds,
            )
        except httpx.HTTPError as exc:
            logger.error(
                "jwks_unavailable",
                extra={"fields": {"error_type": type(exc).__name__, "url": self._settings.stego_auth_jwks_url}},
            )
            raise ApiError(ErrorCode.AUTHORIZATION_UNAVAILABLE) from exc
        if response.status_code != 200:
            logger.error("jwks_bad_status", extra={"fields": {"status": response.status_code}})
            raise ApiError(ErrorCode.AUTHORIZATION_UNAVAILABLE)
        try:
            payload = response.json()
        except ValueError as exc:
            logger.error("jwks_not_json")
            raise ApiError(ErrorCode.AUTHORIZATION_UNAVAILABLE) from exc
        keys = payload.get("keys") if isinstance(payload, dict) else None
        if not isinstance(keys, list):
            logger.error("jwks_invalid_body")
            raise ApiError(ErrorCode.AUTHORIZATION_UNAVAILABLE)

        parsed: dict[str, Any] = {}
        for entry in keys:
            if not isinstance(entry, dict) or entry.get("kty") != "RSA":
                continue
            kid = entry.get("kid")
            if not isinstance(kid, str) or not kid:
                continue
            if entry.get("alg") not in (None, ALLOWED_ALGORITHM):
                continue
            if entry.get("use") not in (None, "sig"):
                continue
            try:
                parsed[kid] = RSAAlgorithm.from_jwk(json.dumps(entry))
            except (InvalidKeyError, ValueError, KeyError, TypeError):
                continue
        if not parsed:
            logger.error("jwks_without_usable_keys")
            raise ApiError(ErrorCode.AUTHORIZATION_UNAVAILABLE)
        self._keys = parsed
        self._expires_at = time.monotonic() + self._settings.stego_jwks_cache_seconds
        logger.info("jwks_loaded", extra={"fields": {"keys": len(parsed)}})


class ServiceTokenClient:
    """Token de servicio con renovación anticipada (contrato 2 §2)."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._client = client
        self._token: str | None = None
        self._refresh_at = 0.0
        self._lock = asyncio.Lock()

    @property
    def next_refresh_in_seconds(self) -> float:
        """Segundos que faltan para la renovación anticipada (0 si no hay token)."""
        if self._token is None:
            return 0.0
        return max(0.0, self._refresh_at - time.monotonic())

    async def get_token(self) -> str:
        if self._token is not None and time.monotonic() < self._refresh_at:
            return self._token
        async with self._lock:
            if self._token is not None and time.monotonic() < self._refresh_at:
                return self._token
            await self._refresh()
        assert self._token is not None
        return self._token

    async def _refresh(self) -> None:
        started = time.perf_counter()
        body = {
            "client_id": self._settings.stego_service_client_id,
            "client_secret": self._settings.stego_service_client_secret,
        }
        try:
            response = await self._client.post(
                self._settings.service_token_url,
                json=body,
                timeout=self._settings.authz_timeout_seconds,
            )
        except httpx.HTTPError as exc:
            self._token = None
            logger.error(
                "service_token_unavailable",
                extra={"fields": {"error_type": type(exc).__name__}},
            )
            raise ApiError(ErrorCode.AUTHORIZATION_UNAVAILABLE) from exc

        if response.status_code != 200:
            self._token = None
            logger.error("service_token_rejected", extra={"fields": {"status": response.status_code}})
            raise ApiError(ErrorCode.AUTHORIZATION_UNAVAILABLE)
        try:
            payload = ServiceTokenResponse.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            self._token = None
            logger.error("service_token_invalid_body")
            raise ApiError(ErrorCode.AUTHORIZATION_UNAVAILABLE) from exc
        if payload.token_type.strip().lower() != "bearer":
            self._token = None
            logger.error("service_token_invalid_grant", extra={"fields": {"token_type": payload.token_type}})
            raise ApiError(ErrorCode.AUTHORIZATION_UNAVAILABLE)

        claims = _decode_payload(payload.access_token)
        if claims.get("token_use") != SERVICE_TOKEN_USE:
            self._token = None
            logger.error("service_token_wrong_use", extra={"fields": {"token_use": claims.get("token_use")}})
            raise ApiError(ErrorCode.AUTHORIZATION_UNAVAILABLE)
        audience = claims.get("aud")
        audiences = [audience] if isinstance(audience, str) else audience
        if not isinstance(audiences, list) or SERVICE_TOKEN_AUDIENCE not in audiences:
            logger.warning("service_token_unexpected_audience")

        remaining = payload.expires_in - self._settings.stego_service_token_min_remaining_seconds
        refresh_in = min(self._settings.service_token_refresh_seconds, max(1, remaining))
        self._token = payload.access_token
        self._refresh_at = time.monotonic() + refresh_in
        logger.info(
            "service_token_obtained",
            extra={
                "fields": {
                    "expires_in": payload.expires_in,
                    "refresh_in_seconds": refresh_in,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                }
            },
        )


class AuthorizationClient:
    """Decisión de autorización por petición (contrato 2 §3), sin caché ni reintentos."""

    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient,
        tokens: ServiceTokenClient,
    ) -> None:
        self._settings = settings
        self._client = client
        self._tokens = tokens

    async def check(
        self,
        *,
        subject_token: str,
        subject_id: uuid.UUID,
        action: str,
        resource_id: uuid.UUID | None,
        request_id: str,
    ) -> AuthorizationDecision:
        started = time.perf_counter()
        service_token = await self._tokens.get_token()
        upstream_id = upstream_request_id(request_id)
        body = {
            "subject_token": subject_token,
            "action": action,
            "resource_id": str(resource_id) if resource_id is not None else None,
        }
        headers = {
            "Authorization": f"Bearer {service_token}",
            "Content-Type": "application/json",
            "X-Request-Id": upstream_id,
        }
        try:
            response = await self._client.post(
                self._settings.authorization_url,
                json=body,
                headers=headers,
                timeout=self._settings.authz_timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            self._log_failure(request_id, upstream_id, action, "timeout")
            raise ApiError(ErrorCode.AUTHORIZATION_UNAVAILABLE) from exc
        except httpx.HTTPError as exc:
            self._log_failure(request_id, upstream_id, action, type(exc).__name__)
            raise ApiError(ErrorCode.AUTHORIZATION_UNAVAILABLE) from exc

        if response.status_code != 200:
            self._log_failure(request_id, upstream_id, action, f"http_{response.status_code}")
            raise ApiError(ErrorCode.AUTHORIZATION_UNAVAILABLE)
        try:
            decision = AuthorizationDecision.model_validate(response.json())
        except (ValueError, ValidationError):
            self._log_failure(request_id, upstream_id, action, "invalid_body")
            raise ApiError(ErrorCode.AUTHORIZATION_UNAVAILABLE)

        self._verify_decision(decision, subject_id=subject_id, action=action, resource_id=resource_id,
                              request_id=request_id, upstream_id=upstream_id)
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        audit.info(
            "authorization_decision",
            extra={
                "fields": {
                    "request_id": request_id,
                    "upstream_request_id": upstream_id,
                    "decision_id": str(decision.decision_id),
                    "subject_id": str(decision.subject_id) if decision.subject_id else None,
                    "action": decision.action,
                    "resource_id": str(decision.resource_id) if decision.resource_id else None,
                    "allowed": decision.allowed,
                    "reason": decision.reason,
                    "roles": decision.roles,
                    "latency_ms": latency_ms,
                    "service": "stego",
                }
            },
        )
        return decision

    def _verify_decision(
        self,
        decision: AuthorizationDecision,
        *,
        subject_id: uuid.UUID,
        action: str,
        resource_id: uuid.UUID | None,
        request_id: str,
        upstream_id: str,
    ) -> None:
        coherent = (
            decision.action == action
            and decision.resource_id == resource_id
            and (decision.subject_id is None or decision.subject_id == subject_id)
        )
        if coherent:
            return
        self._log_failure(request_id, upstream_id, action, "incoherent_decision")
        raise ApiError(ErrorCode.AUTHORIZATION_UNAVAILABLE)

    def _log_failure(self, request_id: str, upstream_id: str, action: str, reason: str) -> None:
        logger.error(
            "authorization_unavailable",
            extra={
                "fields": {
                    "request_id": request_id,
                    "upstream_request_id": upstream_id,
                    "action": action,
                    "reason": reason,
                    "service": "stego",
                }
            },
        )


def decision_to_error(decision: AuthorizationDecision) -> ApiError | None:
    """Traduce una decisión denegada al código del contrato 2 §5."""
    if decision.allowed:
        return None
    reason = decision.reason
    if reason == "token_expired":
        return ApiError(ErrorCode.TOKEN_EXPIRED)
    if reason in ("token_invalid", "subject_not_found"):
        return ApiError(ErrorCode.TOKEN_INVALID)
    if decision.subject_id is None:
        return ApiError(ErrorCode.TOKEN_INVALID)
    if reason == "user_inactive":
        return ApiError(ErrorCode.SUBJECT_INACTIVE)
    return ApiError(ErrorCode.FORBIDDEN)
