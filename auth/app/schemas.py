import uuid
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field

ItemT = TypeVar("ItemT")


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int


class ServiceTokenRequest(BaseModel):
    client_id: str = Field(min_length=1, max_length=64)
    client_secret: str = Field(min_length=1, max_length=256)


class AuthzCheckRequest(BaseModel):
    subject_token: str = Field(min_length=1, max_length=4096)
    action: str = Field(min_length=1, max_length=64)
    resource_id: uuid.UUID | None = None


class AuthzCheckResponse(BaseModel):
    decision_id: uuid.UUID
    subject_id: uuid.UUID | None
    action: str
    resource_id: uuid.UUID | None
    allowed: bool
    reason: str
    roles: list[str]
    decided_at: str
    decision_ttl_seconds: int


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)
    status: str = Field(default="active", pattern="^(active|inactive|locked)$")


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=12, max_length=256)
    status: str | None = Field(default=None, pattern="^(active|inactive|locked)$")


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    email: str
    status: str
    created_at: datetime


class ProfileOut(BaseModel):
    id: uuid.UUID
    username: str
    email: str
    status: str
    roles: list[str]


class RoleCreate(BaseModel):
    name: str = Field(pattern="^[A-Z][A-Z0-9_]{2,31}$")
    description: str | None = Field(default=None, max_length=256)


class RoleUpdate(BaseModel):
    description: str | None = Field(default=None, max_length=256)
    status: str | None = Field(default=None, pattern="^(active|inactive)$")


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    status: str
    created_at: datetime


class UserRoleCreate(BaseModel):
    user_id: uuid.UUID
    role_id: uuid.UUID


class UserRoleUpdate(BaseModel):
    status: str = Field(pattern="^(active|inactive)$")


class UserRoleOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    role_id: uuid.UUID
    status: str
    assigned_at: datetime


class Page(BaseModel, Generic[ItemT]):
    items: list[ItemT]
    page: int
    limit: int
    total: int
