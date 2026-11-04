"""Envoltorio de error único de STEGO (contrato 7 §6) y catálogo de códigos.

Solo se usan códigos del catálogo congelado. Las respuestas nunca incluyen
trazas, rutas internas, SQL ni valores de configuración.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.timeutils import format_utc, utcnow

logger = logging.getLogger("stego.errors")

SERVICE_NAME = "stego"


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    TOKEN_MISSING = "TOKEN_MISSING"
    TOKEN_INVALID = "TOKEN_INVALID"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    TOKEN_REVOKED = "TOKEN_REVOKED"
    SUBJECT_INACTIVE = "SUBJECT_INACTIVE"
    FORBIDDEN = "FORBIDDEN"
    RESULT_FORBIDDEN = "RESULT_FORBIDDEN"
    RESULT_NOT_FOUND = "RESULT_NOT_FOUND"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    FILE_SIGNATURE_MISMATCH = "FILE_SIGNATURE_MISMATCH"
    IMAGE_UNPROCESSABLE = "IMAGE_UNPROCESSABLE"
    AUTHORIZATION_UNAVAILABLE = "AUTHORIZATION_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


_HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.VALIDATION_ERROR: 422,
    ErrorCode.TOKEN_MISSING: 401,
    ErrorCode.TOKEN_INVALID: 401,
    ErrorCode.TOKEN_EXPIRED: 401,
    ErrorCode.TOKEN_REVOKED: 401,
    ErrorCode.SUBJECT_INACTIVE: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.RESULT_FORBIDDEN: 403,
    ErrorCode.RESULT_NOT_FOUND: 404,
    ErrorCode.PAYLOAD_TOO_LARGE: 413,
    ErrorCode.UNSUPPORTED_MEDIA_TYPE: 415,
    ErrorCode.FILE_SIGNATURE_MISMATCH: 415,
    ErrorCode.IMAGE_UNPROCESSABLE: 422,
    ErrorCode.AUTHORIZATION_UNAVAILABLE: 503,
    ErrorCode.INTERNAL_ERROR: 500,
}

_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.VALIDATION_ERROR: "La petición no es válida.",
    ErrorCode.TOKEN_MISSING: "Falta el token de acceso.",
    ErrorCode.TOKEN_INVALID: "El token de acceso no es válido.",
    ErrorCode.TOKEN_EXPIRED: "El token de acceso ha vencido.",
    ErrorCode.TOKEN_REVOKED: "El token de acceso fue revocado.",
    ErrorCode.SUBJECT_INACTIVE: "El usuario está inactivo.",
    ErrorCode.FORBIDDEN: "No tiene permiso para realizar esta operación.",
    ErrorCode.RESULT_FORBIDDEN: "El resultado pertenece a otro usuario.",
    ErrorCode.RESULT_NOT_FOUND: "El resultado no existe.",
    ErrorCode.PAYLOAD_TOO_LARGE: "El archivo supera el límite permitido.",
    ErrorCode.UNSUPPORTED_MEDIA_TYPE: "El tipo de archivo no está permitido.",
    ErrorCode.FILE_SIGNATURE_MISMATCH: "La firma del archivo no coincide con el tipo declarado.",
    ErrorCode.IMAGE_UNPROCESSABLE: "La imagen no se pudo decodificar.",
    ErrorCode.AUTHORIZATION_UNAVAILABLE: "No fue posible obtener una decisión de autorización.",
    ErrorCode.INTERNAL_ERROR: "Error interno del servicio.",
}


class ApiError(Exception):
    """Error de negocio con código del catálogo y estado HTTP asociado."""

    def __init__(
        self,
        code: ErrorCode,
        *,
        message: str | None = None,
        details: list[dict[str, Any]] | None = None,
        status_code: int | None = None,
    ) -> None:
        self.code = code
        self.status_code = status_code or _HTTP_STATUS[code]
        self.message = message or _MESSAGES[code]
        self.details = details or []
        super().__init__(self.message)

    def envelope(self, request_id: str) -> dict[str, Any]:
        error: dict[str, Any] = {
            "code": self.code.value,
            "message": self.message,
            "request_id": request_id,
            "timestamp": format_utc(utcnow()),
        }
        if self.details:
            error["details"] = self.details
        return {"error": error}


def error_envelope(
    request_id: str,
    code: ErrorCode,
    message: str,
    details: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return ApiError(code, message=message, details=details).envelope(request_id)


def _http_code_for_status(status_code: int) -> ErrorCode:
    if status_code == 401:
        return ErrorCode.TOKEN_INVALID
    if status_code == 403:
        return ErrorCode.FORBIDDEN
    if status_code == 404:
        return ErrorCode.RESULT_NOT_FOUND
    if status_code == 413:
        return ErrorCode.PAYLOAD_TOO_LARGE
    if status_code == 415:
        return ErrorCode.UNSUPPORTED_MEDIA_TYPE
    if status_code == 429:
        return ErrorCode.VALIDATION_ERROR
    if status_code >= 500:
        return ErrorCode.INTERNAL_ERROR
    return ErrorCode.VALIDATION_ERROR


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", None) or "")


def _error_response(request: Request, error: ApiError) -> JSONResponse:
    response = JSONResponse(status_code=error.status_code, content=error.envelope(_request_id(request)))
    response.headers["X-Request-Id"] = _request_id(request)
    return response


async def api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    if exc.status_code >= 500:
        logger.error(
            "api_error",
            extra={"fields": {"request_id": _request_id(request), "code": exc.code.value,
                              "status": exc.status_code}},
        )
    return _error_response(request, exc)


async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    details: list[dict[str, Any]] = []
    for issue in exc.errors():
        location = ".".join(str(part) for part in issue.get("loc", ()) if part not in ("body", "query", "path"))
        details.append({"field": location or "request", "issue": str(issue.get("type", "invalid"))})
    error = ApiError(ErrorCode.VALIDATION_ERROR, details=details or None)
    return _error_response(request, error)


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = _http_code_for_status(exc.status_code)
    message = _MESSAGES[code]
    return _error_response(request, ApiError(code, message=message, status_code=exc.status_code))


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled_exception",
        extra={"fields": {"request_id": _request_id(request), "error_type": type(exc).__name__}},
        exc_info=exc,
    )
    return _error_response(request, ApiError(ErrorCode.INTERNAL_ERROR))


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
