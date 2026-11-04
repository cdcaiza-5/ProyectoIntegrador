import uuid
from contextvars import ContextVar
from datetime import datetime, timezone

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

REQUEST_ID: ContextVar[str] = ContextVar("request_id", default="")

MESSAGES: dict[str, str] = {
    "VALIDATION_ERROR": "La solicitud no cumple el contrato.",
    "TOKEN_MISSING": "Falta el token de acceso.",
    "TOKEN_INVALID": "El token no es válido.",
    "TOKEN_EXPIRED": "El token expiró.",
    "TOKEN_REVOKED": "El token fue revocado.",
    "SUBJECT_INACTIVE": "El usuario está desactivado.",
    "AUTH_INVALID_CREDENTIALS": "Credenciales inválidas.",
    "FORBIDDEN": "No tienes permiso para esta operación.",
    "RESULT_FORBIDDEN": "No puedes acceder a un resultado ajeno.",
    "USER_NOT_FOUND": "El usuario no existe.",
    "ROLE_NOT_FOUND": "El rol no existe.",
    "ASSIGNMENT_NOT_FOUND": "La asignación no existe.",
    "RESULT_NOT_FOUND": "El resultado no existe.",
    "USER_EXISTS": "El nombre de usuario ya existe.",
    "EMAIL_EXISTS": "El correo ya está registrado.",
    "ROLE_EXISTS": "El rol ya existe.",
    "ASSIGNMENT_EXISTS": "La asignación ya existe.",
    "ROLE_IN_USE": "El rol está asignado y no se puede eliminar.",
    "PAYLOAD_TOO_LARGE": "El archivo supera el tamaño permitido.",
    "UNSUPPORTED_MEDIA_TYPE": "El tipo de archivo no está permitido.",
    "FILE_SIGNATURE_MISMATCH": "La firma del archivo no coincide con su extensión.",
    "IMAGE_UNPROCESSABLE": "La imagen no se pudo procesar.",
    "RATE_LIMITED": "Demasiadas solicitudes; espera un momento.",
    "SERVICE_AUTH_FAILED": "La autenticación del servicio falló.",
    "AUTHORIZATION_UNAVAILABLE": "La autorización no está disponible.",
    "INTERNAL_ERROR": "Error interno.",
}


def current_request_id() -> str:
    value = REQUEST_ID.get()
    return value or str(uuid.uuid4())


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str | None = None,
        details: list[dict] | None = None,
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message = message or MESSAGES.get(code, code)
        self.details = details


def error_body(code: str, message: str | None = None, details: list[dict] | None = None) -> dict:
    payload: dict = {
        "code": code,
        "message": message or MESSAGES.get(code, code),
        "request_id": current_request_id(),
        "timestamp": utc_timestamp(),
    }
    if details:
        payload["details"] = details
    return {"error": payload}


async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code, content=error_body(exc.code, exc.message, exc.details)
    )


async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        {"field": ".".join(str(part) for part in item.get("loc", ())), "issue": item.get("msg", "")}
        for item in exc.errors()
    ]
    return JSONResponse(status_code=422, content=error_body("VALIDATION_ERROR", details=details))


async def unhandled_error_handler(_: Request, __: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content=error_body("INTERNAL_ERROR"))
