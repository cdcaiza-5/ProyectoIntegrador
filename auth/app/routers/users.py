import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_action
from ..errors import ApiError
from ..models import User
from ..schemas import Page, UserCreate, UserOut, UserUpdate
from ..security import hash_password

router = APIRouter(tags=["users"])


def _taken(session: Session, *, username: str | None, email: str | None, exclude: uuid.UUID | None = None) -> None:
    if username:
        statement = select(User.id).where(func.lower(User.username) == username.lower())
        if exclude:
            statement = statement.where(User.id != exclude)
        if session.scalar(statement) is not None:
            raise ApiError(409, "USER_EXISTS")
    if email:
        statement = select(User.id).where(func.lower(User.email) == email.lower())
        if exclude:
            statement = statement.where(User.id != exclude)
        if session.scalar(statement) is not None:
            raise ApiError(409, "EMAIL_EXISTS")


@router.post("/api/v1/users", response_model=UserOut, status_code=201)
def create_user(
    payload: UserCreate,
    _: dict = Depends(require_action("users.create")),
    session: Session = Depends(get_db),
) -> User:
    _taken(session, username=payload.username, email=payload.email)
    user = User(
        username=payload.username,
        email=str(payload.email),
        password_hash=hash_password(payload.password),
        status=payload.status,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@router.get("/api/v1/users", response_model=Page[UserOut])
def list_users(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    _: dict = Depends(require_action("users.list")),
    session: Session = Depends(get_db),
) -> Page[UserOut]:
    total = session.scalar(select(func.count()).select_from(User)) or 0
    rows = session.scalars(
        select(User).order_by(User.created_at).offset((page - 1) * limit).limit(limit)
    ).all()
    return Page[UserOut](
        items=[UserOut.model_validate(row) for row in rows], page=page, limit=limit, total=total
    )


@router.patch("/api/v1/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    _: dict = Depends(require_action("users.update")),
    session: Session = Depends(get_db),
) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise ApiError(404, "USER_NOT_FOUND")
    _taken(session, username=None, email=str(payload.email) if payload.email else None, exclude=user_id)
    if payload.email is not None:
        user.email = str(payload.email)
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
    if payload.status is not None:
        user.status = payload.status
    session.commit()
    session.refresh(user)
    return user
