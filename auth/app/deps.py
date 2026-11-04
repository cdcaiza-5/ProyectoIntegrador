import uuid
from collections.abc import Callable

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .db import get_db
from .errors import ApiError
from .models import RevokedToken, User
from .rbac import decide
from .security import TokenError, decode_token

bearer_scheme = HTTPBearer(auto_error=False)


def user_token(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)) -> str:
    if credentials is None or not credentials.credentials:
        raise ApiError(401, "TOKEN_MISSING")
    return credentials.credentials


def current_claims(
    token: str = Depends(user_token), session: Session = Depends(get_db)
) -> dict:
    try:
        claims = decode_token(token, "auth-api")
    except TokenError as exc:
        raise ApiError(401, exc.code) from exc

    if session.get(RevokedToken, uuid.UUID(str(claims["jti"]))) is not None:
        raise ApiError(401, "TOKEN_REVOKED")

    user = session.get(User, uuid.UUID(str(claims["sub"])))
    if user is None:
        raise ApiError(401, "TOKEN_INVALID")
    if user.status != "active":
        raise ApiError(401, "SUBJECT_INACTIVE")
    return claims


def require_action(action: str) -> Callable[..., dict]:
    def dependency(
        claims: dict = Depends(current_claims), session: Session = Depends(get_db)
    ) -> dict:
        decision = decide(session, uuid.UUID(str(claims["sub"])), action)
        if not decision.allowed:
            raise ApiError(403, "FORBIDDEN")
        return claims

    return dependency
