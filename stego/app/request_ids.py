"""Identificadores de trazabilidad (contrato 7 §5, contrato 2 §3).

STEGO acepta ``X-Request-Id`` solo si cumple ``^[A-Za-z0-9._-]{1,64}$``; si no,
genera uno. AUTH exige un UUID v4 en su propio ``X-Request-Id``, así que cuando
el identificador entrante no tiene esa forma se genera un UUID v4 para la
llamada interna y se registra la correspondencia.
"""

from __future__ import annotations

import re
import uuid

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_UUID4_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)

HEADER_NAME = "X-Request-Id"


def new_request_id() -> str:
    return str(uuid.uuid4())


def resolve_request_id(value: str | None) -> str:
    if value is not None and REQUEST_ID_PATTERN.fullmatch(value):
        return value
    return new_request_id()


def upstream_request_id(request_id: str) -> str:
    if _UUID4_PATTERN.fullmatch(request_id):
        return request_id
    return new_request_id()
