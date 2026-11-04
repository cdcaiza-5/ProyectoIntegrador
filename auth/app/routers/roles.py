import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_action
from ..errors import ApiError
from ..models import Role
from ..schemas import Page, RoleCreate, RoleOut, RoleUpdate

router = APIRouter(tags=["roles"])


@router.post("/api/v1/roles", response_model=RoleOut, status_code=201)
def create_role(
    payload: RoleCreate,
    _: dict = Depends(require_action("roles.create")),
    session: Session = Depends(get_db),
) -> Role:
    exists = session.scalar(select(Role.id).where(func.lower(Role.name) == payload.name.lower()))
    if exists is not None:
        raise ApiError(409, "ROLE_EXISTS")
    role = Role(name=payload.name, description=payload.description)
    session.add(role)
    session.commit()
    session.refresh(role)
    return role


@router.get("/api/v1/roles", response_model=Page[RoleOut])
def list_roles(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    _: dict = Depends(require_action("roles.list")),
    session: Session = Depends(get_db),
) -> Page[RoleOut]:
    total = session.scalar(select(func.count()).select_from(Role)) or 0
    rows = session.scalars(
        select(Role).order_by(Role.name).offset((page - 1) * limit).limit(limit)
    ).all()
    return Page[RoleOut](
        items=[RoleOut.model_validate(row) for row in rows], page=page, limit=limit, total=total
    )


@router.patch("/api/v1/roles/{role_id}", response_model=RoleOut)
def update_role(
    role_id: uuid.UUID,
    payload: RoleUpdate,
    _: dict = Depends(require_action("roles.update")),
    session: Session = Depends(get_db),
) -> Role:
    role = session.get(Role, role_id)
    if role is None:
        raise ApiError(404, "ROLE_NOT_FOUND")
    if payload.description is not None:
        role.description = payload.description
    if payload.status is not None:
        role.status = payload.status
    session.commit()
    session.refresh(role)
    return role
