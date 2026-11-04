import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..errors import ApiError
from ..models import RevokedToken, ServiceClient, User
from ..ratelimit import SlidingWindowLimiter
from ..rbac import decide
from ..schemas import AuthzCheckRequest, AuthzCheckResponse, ServiceTokenRequest, TokenResponse
from ..security import TokenError, decode_token, issue_service_token, verify_password

router = APIRouter(tags=["internal"])
bearer_scheme = HTTPBearer(auto_error=False)
token_limiter = SlidingWindowLimiter(30, 60)


def _authenticate_service(
    credentials: HTTPAuthorizationCredentials | None, session: Session
) -> ServiceClient:
    if credentials is None or not credentials.credentials:
        raise ApiError(401, "SERVICE_AUTH_FAILED")
    try:
        claims = decode_token(credentials.credentials, "auth-internal", expected_use="service")
    except TokenError as exc:
        raise ApiError(401, "SERVICE_AUTH_FAILED") from exc

    client_id = str(claims["sub"]).removeprefix("service:")
    client = session.get(ServiceClient, client_id)
    if client is None or client.status != "active":
        raise ApiError(401, "SERVICE_AUTH_FAILED")
    return client


@router.post("/internal/service-token", response_model=TokenResponse)
def service_token(payload: ServiceTokenRequest, session: Session = Depends(get_db)) -> TokenResponse:
    if not token_limiter.allow(payload.client_id):
        raise ApiError(429, "RATE_LIMITED")

    client = session.get(ServiceClient, payload.client_id)
    valid = verify_password(payload.client_secret, client.secret_hash if client else None)
    if not valid or client is None or client.status != "active":
        raise ApiError(401, "SERVICE_AUTH_FAILED")

    token, _ = issue_service_token(client.client_id)
    return TokenResponse(
        access_token=token, expires_in=get_settings().auth_service_token_ttl_seconds
    )


@router.post("/internal/authorization/check", response_model=AuthzCheckResponse)
def authorization_check(
    payload: AuthzCheckRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_db),
) -> AuthzCheckResponse:
    _authenticate_service(credentials, session)

    settings = get_settings()
    decision_id = uuid.uuid4()
    subject_id: uuid.UUID | None = None
    allowed = False
    reason = "token_invalid"
    roles: list[str] = []

    try:
        claims = decode_token(payload.subject_token, "auth-api")
    except TokenError as exc:
        reason = "token_expired" if exc.code == "TOKEN_EXPIRED" else "token_invalid"
    else:
        subject_id = uuid.UUID(str(claims["sub"]))
        if session.get(RevokedToken, uuid.UUID(str(claims["jti"]))) is not None:
            reason = "token_invalid"
        else:
            decision = decide(session, subject_id, payload.action)
            allowed = decision.allowed
            reason = decision.reason
            roles = decision.roles

    return AuthzCheckResponse(
        decision_id=decision_id,
        subject_id=subject_id,
        action=payload.action,
        resource_id=payload.resource_id,
        allowed=allowed,
        reason=reason,
        roles=roles,
        decided_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        decision_ttl_seconds=settings.auth_authz_decision_ttl_seconds,
    )
