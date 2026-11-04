"""Esquemas de entrada/salida.

``AnalysisResult`` refleja exactamente ``contracts/analysis-result.schema.json``
(``additionalProperties: false``): los doce campos, ni uno más.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.models import Analysis
from app.timeutils import format_utc

AnalysisStatus = Literal["sin_indicios", "sospechosos", "no_concluyentes", "error"]
AnalysisAction = Literal["ninguna", "advertencia", "cuarentena", "rechazo"]
CanonicalContentType = Literal["image/png", "image/bmp"]

AuthorizationReason = Literal[
    "active_role_grants_permission",
    "no_active_role_for_action",
    "user_inactive",
    "role_inactive",
    "assignment_missing",
    "assignment_inactive",
    "unknown_action",
    "token_invalid",
    "token_expired",
    "subject_not_found",
]


class AnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    analysis_id: uuid.UUID
    user_id: uuid.UUID
    filename: str = Field(min_length=1, max_length=255)
    content_type: CanonicalContentType
    size_bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    technique: Literal["lsb_statistical_analysis"]
    status: AnalysisStatus
    indicators: dict[str, int | float]
    action: AnalysisAction
    limitations: str = Field(min_length=1)
    created_at: datetime

    @field_serializer("created_at")
    def _serialize_created_at(self, value: datetime) -> str:
        return format_utc(value)

    @classmethod
    def from_row(cls, row: Analysis) -> "AnalysisResult":
        return cls(
            analysis_id=row.analysis_id,
            user_id=row.user_id,
            filename=row.filename,
            content_type=row.content_type,
            size_bytes=row.size_bytes,
            sha256=row.sha256,
            technique=row.technique,
            status=row.status,
            indicators=row.indicators,
            action=row.action,
            limitations=row.limitations,
            created_at=row.created_at,
        )


class AuthorizationDecision(BaseModel):
    """Respuesta de AUTH a ``/internal/authorization/check`` (contrato 2 §3)."""

    model_config = ConfigDict(extra="ignore")

    decision_id: uuid.UUID
    subject_id: uuid.UUID | None
    action: str
    resource_id: uuid.UUID | None
    allowed: bool
    reason: AuthorizationReason
    roles: list[Literal["ADMIN", "ANALYST", "USER"]]
    decided_at: datetime
    decision_ttl_seconds: int


class ServiceTokenResponse(BaseModel):
    """Respuesta de AUTH a ``/internal/service-token`` (contrato 3)."""

    model_config = ConfigDict(extra="ignore")

    access_token: str = Field(min_length=20)
    token_type: str
    expires_in: int = Field(gt=0)

    @property
    def expires_in_seconds(self) -> int:
        return self.expires_in
