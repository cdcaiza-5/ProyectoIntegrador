import logging
import re
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError

from .config import get_settings
from .db import SessionLocal
from .errors import (
    REQUEST_ID,
    ApiError,
    api_error_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from .models import ServiceClient
from .routers import auth as auth_routes
from .routers import internal, roles, user_roles, users
from .security import dummy_hash, hash_password

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
logger = logging.getLogger("auth")


def _ensure_service_client() -> None:
    settings = get_settings()
    if not settings.auth_service_client_secret:
        return
    with SessionLocal() as session:
        if session.get(ServiceClient, settings.auth_service_client_id) is None:
            session.add(
                ServiceClient(
                    client_id=settings.auth_service_client_id,
                    secret_hash=hash_password(settings.auth_service_client_secret),
                )
            )
            session.commit()
            logger.info("cliente de servicio aprovisionado: %s", settings.auth_service_client_id)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logging.basicConfig(level=get_settings().auth_log_level.upper())
    dummy_hash()
    try:
        _ensure_service_client()
    except Exception:
        logger.warning("no se pudo aprovisionar el cliente de servicio en el arranque")
    yield


app = FastAPI(
    title="AUTH",
    description="Identidad, roles, JWT y decisiones de autorización RBAC.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    incoming = request.headers.get("x-request-id", "")
    request_id = incoming if REQUEST_ID_PATTERN.match(incoming) else str(uuid.uuid4())
    REQUEST_ID.set(request_id)
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    return response


app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(Exception, unhandled_error_handler)

app.include_router(auth_routes.router)
app.include_router(users.router)
app.include_router(roles.router)
app.include_router(user_roles.router)
app.include_router(internal.router)


@app.get("/health", include_in_schema=False)
def health() -> dict[str, str]:
    return {"status": "ok", "service": "auth"}
