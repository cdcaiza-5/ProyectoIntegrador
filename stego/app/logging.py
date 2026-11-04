"""Registro estructurado en JSON, con redacción de secretos.

Reglas del contrato 7 §7/§9: ninguna línea incluye contraseñas, claves, JWT
completos ni cadenas de conexión; tampoco se registra el contenido de los
archivos analizados ni rutas internas completas.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import traceback
from datetime import UTC, datetime
from typing import Any

from app.timeutils import format_utc

SERVICE_NAME = "stego"

_URL_CREDENTIALS = re.compile(r"([a-z][a-z0-9+.\-]*://[^:/@\s]+:)[^@/\s]+@", re.IGNORECASE)
_BEARER = re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=\-]{8,}")
_ASSIGNMENT = re.compile(r"(?i)\b(password|passwd|secret|client_secret|access_token|refresh_token)\s*[=:]\s*\S+")
_SENSITIVE_KEYS = ("password", "secret", "token", "authorization", "cookie", "key")

_SERVICE_NAME = SERVICE_NAME


def redact(value: str) -> str:
    text = _URL_CREDENTIALS.sub(r"\1***@", value)
    text = _BEARER.sub(r"\1***", text)
    return _ASSIGNMENT.sub(r"\1=***", text)


def _redact_value(key: str, value: Any) -> Any:
    lowered = key.lower()
    if any(marker in lowered for marker in _SENSITIVE_KEYS):
        return "***"
    if isinstance(value, str):
        return redact(value)
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": format_utc(datetime.now(UTC)),
            "level": record.levelname.lower(),
            "service": _SERVICE_NAME,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update({str(key): _redact_value(str(key), value) for key, value in fields.items()})
        if record.exc_info:
            payload["error_type"] = getattr(record.exc_info[0], "__name__", "Exception")
            payload["error_message"] = redact(str(record.exc_info[1]))
            payload["traceback"] = redact("".join(traceback.format_exception(*record.exc_info)).strip())
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level_name: str = "info") -> None:
    level = getattr(logging, level_name.strip().upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # Uvicorn conserva sus propios loggers; se alinean con el formato JSON y
    # el acceso se registra en el middleware de la aplicación (con request_id).
    for name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
        logger.setLevel(level)
    access = logging.getLogger("uvicorn.access")
    access.handlers = []
    access.propagate = False
    access.disabled = True

    # httpx registra cada llamada saliente con su URL completa; el detalle de
    # las llamadas a AUTH se registra en stego.auth y stego.audit.
    logging.getLogger("httpx").setLevel(max(level, logging.WARNING))


def audit_logger() -> logging.Logger:
    return logging.getLogger("stego.audit")
