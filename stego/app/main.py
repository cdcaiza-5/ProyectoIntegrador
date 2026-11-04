"""Aplicación FastAPI de STEGO.

Superficie pública (contrato 6 §1 y contrato 7 §4)::

    GET  /health                                  -> {"status": "ok", "service": "stego"}
    POST /api/v1/steganography/analyze            -> 201 analysis-result
    GET  /api/v1/steganography/results/{id}       -> 200 analysis-result

``POST /internal/service-token`` y ``POST /internal/authorization/check`` son de
AUTH: STEGO es el cliente de ambas (app/auth_client.py), no su implementación.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Request
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.auth_client import AuthorizationClient, JwksVerifier, ServiceTokenClient
from app.config import Settings, get_settings
from app.db import Database
from app.errors import register_exception_handlers
from app.logging import configure_logging
from app.request_ids import HEADER_NAME, resolve_request_id
from app.routers import steganography

logger = logging.getLogger("stego.main")
access_logger = logging.getLogger("stego.http")


def _header(scope: Scope, name: str) -> str | None:
    wanted = name.lower().encode("latin-1")
    for key, value in scope.get("headers", []):
        if key.lower() == wanted:
            return value.decode("latin-1")
    return None


class RequestIdMiddleware:
    """Valida/genera ``X-Request-Id``, la devuelve y registra el acceso."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = resolve_request_id(_header(scope, HEADER_NAME))
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        response_status = {"code": 500}

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_status["code"] = message["status"]
                MutableHeaders(scope=message)[HEADER_NAME] = request_id
            await send(message)

        started = time.perf_counter()
        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            path = scope.get("path", "")
            level = logging.DEBUG if path == "/health" else logging.INFO
            access_logger.log(
                level,
                "http_request",
                extra={
                    "fields": {
                        "request_id": request_id,
                        "method": scope.get("method"),
                        "path": path,
                        "status": response_status["code"],
                        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    }
                },
            )


async def _prepare_storage(settings: Settings) -> None:
    try:
        await asyncio.to_thread(
            settings.quarantine_path.mkdir, mode=0o750, parents=True, exist_ok=True
        )
    except OSError as exc:
        logger.error(
            "storage_directory_unavailable",
            extra={"fields": {"error_type": type(exc).__name__}},
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    database = Database(settings.database_url)
    app.state.db = database

    timeout = httpx.Timeout(
        settings.authz_timeout_seconds,
        connect=min(1.0, settings.authz_timeout_seconds),
    )
    http_client = httpx.AsyncClient(timeout=timeout, headers={"User-Agent": "stego/1.0"})
    app.state.http = http_client
    app.state.jwks = JwksVerifier(settings, http_client)
    service_tokens = ServiceTokenClient(settings, http_client)
    app.state.service_tokens = service_tokens
    app.state.authorization = AuthorizationClient(settings, http_client, service_tokens)

    await _prepare_storage(settings)
    await database.check()
    logger.info(
        "service_started",
        extra={
            "fields": {
                "port": settings.stego_http_port,
                "lsb_anomaly_threshold": settings.stego_lsb_anomaly_threshold,
                "max_upload_bytes": settings.stego_max_upload_bytes,
                "authz_timeout_ms": settings.stego_authz_timeout_ms,
            }
        },
    )
    try:
        yield
    finally:
        await http_client.aclose()
        await database.dispose()
        logger.info("service_stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    configure_logging(resolved.stego_log_level)

    application = FastAPI(
        title="STEGO",
        version="1.0.0",
        description=(
            "Servicio de análisis esteganográfico. Valida el archivo, verifica el JWT con "
            "JWKS, obtiene una decisión vigente de AUTH y aplica el ataque chi-cuadrado "
            "sobre los planos LSB. El resultado es indicativo, nunca concluyente."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
    )
    application.state.settings = resolved
    application.add_middleware(RequestIdMiddleware)
    register_exception_handlers(application)
    application.include_router(steganography.router, prefix=resolved.api_v1_str)

    @application.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "stego"}

    @application.get("/", include_in_schema=False)
    def root(request: Request) -> dict[str, Any]:
        return {"service": "stego", "docs": str(request.url_for("swagger_ui_html"))}

    return application


app = create_app()
