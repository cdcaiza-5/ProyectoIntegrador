"""Utilidades de tiempo: todo el servicio trabaja en UTC."""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)


def format_utc(moment: datetime) -> str:
    """ISO-8601 UTC con sufijo ``Z`` (contrato 7 §5)."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")
