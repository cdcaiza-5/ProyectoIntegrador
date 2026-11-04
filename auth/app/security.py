import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.hazmat.primitives import serialization
from jwt.algorithms import RSAAlgorithm

from .config import get_settings

_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16)
_TIMING_EQUALISER = "equalisierung-para-tiempos-de-respuesta"


class TokenError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def hash_password(password: str) -> str:
    return _hasher.hash(password)


@lru_cache
def dummy_hash() -> str:
    return _hasher.hash(_TIMING_EQUALISER)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or dummy_hash(), password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


@lru_cache
def _private_key() -> str:
    return Path(get_settings().auth_jwt_private_key_path).read_text(encoding="utf-8")


@lru_cache
def _public_key() -> str:
    return Path(get_settings().auth_jwt_public_key_path).read_text(encoding="utf-8")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def issue_access_token(user_id: uuid.UUID, username: str) -> tuple[str, uuid.UUID, datetime]:
    settings = get_settings()
    jti = uuid.uuid4()
    issued = _now()
    expires = issued + timedelta(seconds=settings.auth_access_token_ttl_seconds)
    payload = {
        "iss": settings.auth_jwt_issuer,
        "sub": str(user_id),
        "aud": settings.audiences,
        "iat": int(issued.timestamp()),
        "exp": int(expires.timestamp()),
        "jti": str(jti),
        "token_use": "access",
        "username": username,
    }
    token = jwt.encode(
        payload, _private_key(), algorithm="RS256", headers={"kid": settings.auth_jwt_kid, "typ": "JWT"}
    )
    return token, jti, expires


def issue_service_token(client_id: str) -> tuple[str, datetime]:
    settings = get_settings()
    issued = _now()
    expires = issued + timedelta(seconds=settings.auth_service_token_ttl_seconds)
    payload = {
        "iss": settings.auth_jwt_issuer,
        "sub": f"service:{client_id}",
        "aud": ["auth-internal"],
        "iat": int(issued.timestamp()),
        "exp": int(expires.timestamp()),
        "jti": str(uuid.uuid4()),
        "token_use": "service",
    }
    token = jwt.encode(
        payload, _private_key(), algorithm="RS256", headers={"kid": settings.auth_jwt_kid, "typ": "JWT"}
    )
    return token, expires


def decode_token(token: str, audience: str, expected_use: str = "access") -> dict:
    settings = get_settings()
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as exc:
        raise TokenError("TOKEN_INVALID") from exc

    if header.get("alg") != "RS256" or header.get("typ", "JWT") != "JWT":
        raise TokenError("TOKEN_INVALID")
    if header.get("kid") != settings.auth_jwt_kid:
        raise TokenError("TOKEN_INVALID")

    try:
        payload = jwt.decode(
            token,
            _public_key(),
            algorithms=["RS256"],
            audience=audience,
            issuer=settings.auth_jwt_issuer,
            options={"require": ["exp", "iat", "iss", "aud", "sub", "jti"]},
            leeway=60,
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("TOKEN_EXPIRED") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("TOKEN_INVALID") from exc

    if payload.get("token_use") != expected_use:
        raise TokenError("TOKEN_INVALID")
    if expected_use == "access":
        try:
            uuid.UUID(str(payload.get("sub")))
        except (ValueError, TypeError) as exc:
            raise TokenError("TOKEN_INVALID") from exc
    return payload


def public_jwks() -> dict:
    settings = get_settings()
    key = serialization.load_pem_public_key(_public_key().encode())
    jwk = RSAAlgorithm.to_jwk(key, as_dict=True)
    jwk.update({"kid": settings.auth_jwt_kid, "use": "sig", "alg": "RS256"})
    return {"keys": [jwk]}
