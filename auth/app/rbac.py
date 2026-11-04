import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Role, User, UserRole

PERMISSIONS: dict[str, set[str]] = {
    "auth.profile.read": {"ADMIN", "ANALYST", "USER"},
    "auth.logout": {"ADMIN", "ANALYST", "USER"},
    "users.create": {"ADMIN"},
    "users.list": {"ADMIN"},
    "users.update": {"ADMIN"},
    "roles.create": {"ADMIN"},
    "roles.list": {"ADMIN"},
    "roles.update": {"ADMIN"},
    "user_roles.create": {"ADMIN"},
    "user_roles.update": {"ADMIN"},
    "user_roles.delete": {"ADMIN"},
    "steganography.analyze": {"ADMIN", "ANALYST"},
    "steganography.results.read": {"ADMIN", "ANALYST", "USER"},
}


@dataclass
class Decision:
    allowed: bool
    reason: str
    roles: list[str] = field(default_factory=list)


def active_roles(session: Session, user_id: uuid.UUID) -> list[str]:
    statement = (
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(
            UserRole.user_id == user_id,
            UserRole.status == "active",
            Role.status == "active",
        )
    )
    return sorted({name for name in session.scalars(statement)})


def decide(session: Session, subject_id: uuid.UUID, action: str) -> Decision:
    roles = active_roles(session, subject_id)

    if action not in PERMISSIONS:
        return Decision(False, "unknown_action", roles)

    user = session.get(User, subject_id)
    if user is None:
        return Decision(False, "subject_not_found", roles)
    if user.status != "active":
        return Decision(False, "user_inactive", roles)
    if PERMISSIONS[action] & set(roles):
        return Decision(True, "active_role_grants_permission", roles)

    granting = PERMISSIONS[action]
    rows = session.execute(
        select(UserRole, Role)
        .join(Role, Role.id == UserRole.role_id)
        .where(UserRole.user_id == subject_id, Role.name.in_(granting))
    ).all()

    if not rows:
        total = session.scalar(
            select(func.count()).select_from(UserRole).where(UserRole.user_id == subject_id)
        )
        reason = "assignment_missing" if not total else "no_active_role_for_action"
        return Decision(False, reason, roles)
    if any(assignment.status != "active" for assignment, _ in rows):
        return Decision(False, "assignment_inactive", roles)
    if any(role.status != "active" for _, role in rows):
        return Decision(False, "role_inactive", roles)
    return Decision(False, "no_active_role_for_action", roles)
