import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_claims, require_action
from ..errors import ApiError
from ..models import Role, User, UserRole
from ..schemas import UserRoleCreate, UserRoleOut, UserRoleUpdate

router = APIRouter(tags=["user-roles"])


@router.post("/api/v1/user-roles", response_model=UserRoleOut, status_code=201)
def create_assignment(
    payload: UserRoleCreate,
    claims: dict = Depends(require_action("user_roles.create")),
    session: Session = Depends(get_db),
) -> UserRole:
    if session.get(User, payload.user_id) is None:
        raise ApiError(404, "USER_NOT_FOUND")
    if session.get(Role, payload.role_id) is None:
        raise ApiError(404, "ROLE_NOT_FOUND")
    existing = session.scalar(
        select(UserRole).where(
            UserRole.user_id == payload.user_id, UserRole.role_id == payload.role_id
        )
    )
    if existing is not None:
        raise ApiError(409, "ASSIGNMENT_EXISTS")
    assignment = UserRole(
        user_id=payload.user_id,
        role_id=payload.role_id,
        assigned_by=uuid.UUID(str(claims["sub"])),
    )
    session.add(assignment)
    session.commit()
    session.refresh(assignment)
    return assignment


@router.patch("/api/v1/user-roles/{assignment_id}", response_model=UserRoleOut)
def update_assignment(
    assignment_id: uuid.UUID,
    payload: UserRoleUpdate,
    _: dict = Depends(require_action("user_roles.update")),
    session: Session = Depends(get_db),
) -> UserRole:
    assignment = session.get(UserRole, assignment_id)
    if assignment is None:
        raise ApiError(404, "ASSIGNMENT_NOT_FOUND")
    assignment.status = payload.status
    session.commit()
    session.refresh(assignment)
    return assignment


@router.delete("/api/v1/user-roles/{assignment_id}", status_code=204)
def delete_assignment(
    assignment_id: uuid.UUID,
    _: dict = Depends(require_action("user_roles.delete")),
    session: Session = Depends(get_db),
) -> Response:
    assignment = session.get(UserRole, assignment_id)
    if assignment is None:
        raise ApiError(404, "ASSIGNMENT_NOT_FOUND")
    session.delete(assignment)
    session.commit()
    return Response(status_code=204)
