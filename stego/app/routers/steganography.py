"""Endpoints públicos de STEGO (contrato 6 §1)."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.auth_client import (
    ACTION_ANALYZE,
    ACTION_RESULTS_READ,
    AccessToken,
    JwksVerifier,
    decision_to_error,
)
from app.config import Settings
from app.errors import ApiError, ErrorCode
from app.lsb import TECHNIQUE, AnalysisOutcome, analyze_image, error_outcome
from app.models import Analysis
from app.schemas import AnalysisResult
from app.timeutils import utcnow
from app.upload import read_upload, store_quarantined, validate_upload

logger = logging.getLogger("stego.api")
audit = logging.getLogger("stego.audit")

router = APIRouter(prefix="/steganography", tags=["steganography"])

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "TOKEN_MISSING, TOKEN_INVALID, TOKEN_EXPIRED, TOKEN_REVOKED o SUBJECT_INACTIVE"},
    403: {"description": "FORBIDDEN o RESULT_FORBIDDEN"},
    404: {"description": "RESULT_NOT_FOUND"},
    413: {"description": "PAYLOAD_TOO_LARGE"},
    415: {"description": "UNSUPPORTED_MEDIA_TYPE o FILE_SIGNATURE_MISMATCH"},
    422: {"description": "VALIDATION_ERROR o IMAGE_UNPROCESSABLE"},
    503: {"description": "AUTHORIZATION_UNAVAILABLE"},
}

ANALYZE_RESPONSES = {code: ERROR_RESPONSES[code] for code in (401, 403, 413, 415, 422, 503)}
RESULT_RESPONSES = {code: ERROR_RESPONSES[code] for code in (401, 403, 404, 503)}

MULTIPART_REQUEST_BODY: dict[str, Any] = {
    "required": True,
    "content": {
        "multipart/form-data": {
            "schema": {
                "type": "object",
                "required": ["file"],
                "properties": {
                    "file": {
                        "type": "string",
                        "format": "binary",
                        "description": (
                            "Imagen PNG (firma 89 50 4E 47 0D 0A 1A 0A) o BMP (firma 42 4D), "
                            "un único archivo por petición, <= STEGO_MAX_UPLOAD_BYTES."
                        ),
                    },
                    "note": {
                        "type": "string",
                        "maxLength": 500,
                        "description": "Metadato opcional; no altera el análisis.",
                    },
                },
            }
        }
    },
}


async def current_access_token(request: Request) -> AccessToken:
    authorization = request.headers.get("authorization")
    if not authorization:
        raise ApiError(ErrorCode.TOKEN_MISSING)
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        raise ApiError(ErrorCode.TOKEN_INVALID)
    verifier: JwksVerifier = request.app.state.jwks
    return await verifier.verify(parts[1])


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.db.sessions() as session:
        yield session


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "") or "")


@router.post(
    "/analyze",
    status_code=201,
    response_model=AnalysisResult,
    summary="Analizar una imagen PNG o BMP en busca de sustitución LSB",
    responses=ANALYZE_RESPONSES,
    openapi_extra={"requestBody": MULTIPART_REQUEST_BODY},
)
async def analyze(
    request: Request,
    token: Annotated[AccessToken, Depends(current_access_token)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AnalysisResult:
    settings: Settings = request.app.state.settings
    request_id = _request_id(request)

    decision = await request.app.state.authorization.check(
        subject_token=token.raw,
        subject_id=token.subject,
        action=ACTION_ANALYZE,
        resource_id=None,
        request_id=request_id,
    )
    denial = decision_to_error(decision)
    if denial is not None:
        raise denial

    upload = await read_upload(request, settings)
    # `note` se valida (<= 500 caracteres) pero no se persiste: la tabla
    # congelada stego.analyses no tiene columna para metadatos libres.
    validated = await run_in_threadpool(validate_upload, upload, settings)

    stored_path = await run_in_threadpool(
        store_quarantined, validated.data, validated.content_type, settings
    )

    started = time.perf_counter()
    try:
        outcome: AnalysisOutcome = await run_in_threadpool(
            analyze_image,
            validated.image,
            threshold=settings.stego_lsb_anomaly_threshold,
            min_pixels=settings.stego_min_analysis_pixels,
            min_palette_colors=settings.stego_min_palette_colors,
        )
    except Exception as exc:  # noqa: BLE001 - el contrato exige status=error controlado
        logger.error(
            "analysis_failed",
            extra={
                "fields": {
                    "request_id": request_id,
                    "error_type": type(exc).__name__,
                    "content_type": validated.content_type,
                }
            },
        )
        outcome = error_outcome(settings.stego_lsb_anomaly_threshold)
    finally:
        await run_in_threadpool(validated.image.close)

    row = Analysis(
        analysis_id=uuid.uuid4(),
        user_id=token.subject,
        filename=validated.filename,
        stored_path=stored_path,
        sha256=validated.sha256,
        content_type=validated.content_type,
        size_bytes=validated.size_bytes,
        technique=TECHNIQUE,
        status=outcome.status,
        indicators=outcome.indicators,
        action=outcome.action,
        limitations=outcome.limitations,
        created_at=utcnow(),
    )
    session.add(row)
    try:
        await session.commit()
    except SQLAlchemyError as exc:
        await session.rollback()
        logger.error(
            "analysis_persist_failed",
            extra={"fields": {"request_id": request_id, "error_type": type(exc).__name__}},
        )
        raise ApiError(ErrorCode.INTERNAL_ERROR) from exc

    audit.info(
        "analysis_completed",
        extra={
            "fields": {
                "request_id": request_id,
                "analysis_id": str(row.analysis_id),
                "user_id": str(row.user_id),
                "filename": row.filename,
                "content_type": row.content_type,
                "size_bytes": row.size_bytes,
                "sha256_prefix": row.sha256[:12],
                "status": row.status,
                "action": row.action,
                "anomaly_score": outcome.indicators.get("anomaly_score"),
                "estimated_embedding_rate": outcome.indicators.get("estimated_embedding_rate"),
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            }
        },
    )
    return AnalysisResult.from_row(row)


@router.get(
    "/results/{analysis_id}",
    response_model=AnalysisResult,
    summary="Consultar un análisis propio (ADMIN puede ver cualquiera)",
    responses=RESULT_RESPONSES,
)
async def read_result(
    analysis_id: uuid.UUID,
    request: Request,
    token: Annotated[AccessToken, Depends(current_access_token)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AnalysisResult:
    request_id = _request_id(request)
    decision = await request.app.state.authorization.check(
        subject_token=token.raw,
        subject_id=token.subject,
        action=ACTION_RESULTS_READ,
        resource_id=analysis_id,
        request_id=request_id,
    )
    denial = decision_to_error(decision)
    if denial is not None:
        raise denial

    row = await session.get(Analysis, analysis_id)
    if row is None:
        raise ApiError(ErrorCode.RESULT_NOT_FOUND)
    if "ADMIN" not in decision.roles and row.user_id != token.subject:
        audit.info(
            "result_forbidden",
            extra={
                "fields": {
                    "request_id": request_id,
                    "analysis_id": str(analysis_id),
                    "user_id": str(token.subject),
                    "owner_id": str(row.user_id),
                }
            },
        )
        raise ApiError(ErrorCode.RESULT_FORBIDDEN)

    audit.info(
        "result_read",
        extra={
            "fields": {
                "request_id": request_id,
                "analysis_id": str(analysis_id),
                "user_id": str(token.subject),
                "roles": decision.roles,
            }
        },
    )
    return AnalysisResult.from_row(row)
