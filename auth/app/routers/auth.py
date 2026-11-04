import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import current_claims, require_action
from ..errors import ApiError
from ..models import RevokedToken, User
from ..ratelimit import SlidingWindowLimiter
from ..rbac import active_roles
from ..schemas import LoginRequest, ProfileOut, TokenResponse
from ..security import issue_access_token, public_jwks, verify_password

router = APIRouter(tags=["auth"])

login_limiter = SlidingWindowLimiter(get_settings().auth_login_rate_limit_per_minute, 60)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/api/v1/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, session: Session = Depends(get_db)) -> TokenResponse:
    key = f"{_client_ip(request)}:{payload.identifier.lower()}"
    if not login_limiter.allow(key):
        raise ApiError(429, "RATE_LIMITED")

    identifier = payload.identifier.lower()
    user = session.scalar(
        select(User).where(
            or_(func.lower(User.username) == identifier, func.lower(User.email) == identifier)
        )
    )
    valid = verify_password(payload.password, user.password_hash if user else None)
    if not valid or user is None or user.status != "active":
        raise ApiError(401, "AUTH_INVALID_CREDENTIALS")

    token, _, _ = issue_access_token(user.id, user.username)
    return TokenResponse(
        access_token=token, expires_in=get_settings().auth_access_token_ttl_seconds
    )


@router.get("/api/v1/auth/profile", response_model=ProfileOut)
def profile(
    claims: dict = Depends(require_action("auth.profile.read")),
    session: Session = Depends(get_db),
) -> ProfileOut:
    user = session.get(User, uuid.UUID(str(claims["sub"])))
    if user is None:
        raise ApiError(401, "TOKEN_INVALID")
    return ProfileOut(
        id=user.id,
        username=user.username,
        email=user.email,
        status=user.status,
        roles=active_roles(session, user.id),
    )


@router.post("/api/v1/auth/logout", status_code=204)
def logout(
    claims: dict = Depends(require_action("auth.logout")),
    session: Session = Depends(get_db),
) -> Response:
    expires_at = datetime.fromtimestamp(int(claims["exp"]), tz=timezone.utc)
    session.add(
        RevokedToken(
            jti=uuid.UUID(str(claims["jti"])),
            subject_id=uuid.UUID(str(claims["sub"])),
            expires_at=expires_at,
            reason="logout",
        )
    )
    session.commit()
    return Response(status_code=204)


@router.get("/.well-known/jwks.json")
def jwks() -> dict:
    return public_jwks()
