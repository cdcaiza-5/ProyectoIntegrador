"""Ingesta del archivo: pasos 3 a 10 de la tubería de validación (contrato 6 §2).

El orden es obligatorio y corta en el primer fallo::

    3. Content-Type de la petición es multipart/form-data     -> 415
    4. Existe el campo file, uno solo (note opcional <= 500)  -> 422
    5. Tamaño <= STEGO_MAX_UPLOAD_BYTES                       -> 413
    6. Extensión en la lista permitida                        -> 415
    7. Tipo declarado en la lista permitida                   -> 415
    8. Firma real (magic bytes) coherente con el tipo         -> 415 FILE_SIGNATURE_MISMATCH
    9. Decodifica como imagen válida del tipo declarado       -> 422 IMAGE_UNPROCESSABLE
   10. Ancho/alto/píxeles dentro de los límites               -> 413

El resultado es un objeto en memoria: nada se persiste hasta que la validación
completa termina, de modo que un rechazo no deja archivo ni fila en la base.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import unicodedata
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.requests import Request

from app.config import Settings
from app.errors import ApiError, ErrorCode
logger = logging.getLogger("stego.upload")

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
BMP_MAGIC = b"BM"
EXPECTED_FORMATS = {"image/png": "PNG", "image/bmp": "BMP"}
CANONICAL_EXTENSIONS = {"image/png": "png", "image/bmp": "bmp"}
NOTE_MAX_LENGTH = 500
_MULTIPART_OVERHEAD_BYTES = 64 * 1024


@dataclass(frozen=True)
class MultipartUpload:
    filename: str
    declared_content_type: str | None
    data: bytes
    note: str | None = None


@dataclass(frozen=True)
class ValidatedImage:
    filename: str
    declared_content_type: str
    content_type: str
    data: bytes
    size_bytes: int
    sha256: str
    width: int
    height: int
    image: Image.Image = field(repr=False, compare=False)


class _BodyTooLarge(Exception):
    pass


def _require_multipart(request: Request) -> None:
    content_type = request.headers.get("content-type", "")
    media_type = content_type.split(";", 1)[0].strip().lower()
    if media_type != "multipart/form-data":
        raise ApiError(
            ErrorCode.UNSUPPORTED_MEDIA_TYPE,
            details=[{"field": "content-type", "issue": "not_multipart_form_data"}],
        )


async def _limited_stream(request: Request, limit: int) -> AsyncIterator[bytes]:
    """Corta el cuerpo antes de que el parser pueda consumir más del presupuesto."""
    received = 0
    async for chunk in request.stream():
        received += len(chunk)
        if received > limit:
            raise _BodyTooLarge
        yield chunk


async def _parse_form(request: Request, settings: Settings):
    budget = settings.stego_max_upload_bytes + _MULTIPART_OVERHEAD_BYTES
    parser = MultiPartParser(
        request.headers,
        _limited_stream(request, budget),
        max_files=4,
        max_fields=8,
    )
    try:
        return await parser.parse()
    except _BodyTooLarge as exc:
        # El corte por tamaño ocurre antes de conocer el campo: un cuerpo
        # desproporcionado se rechaza por 413 aunque además fuese inválido.
        raise ApiError(
            ErrorCode.PAYLOAD_TOO_LARGE,
            details=[{"field": "file", "issue": "size_exceeds_limit"}],
        ) from exc
    except MultiPartException as exc:
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            message="El cuerpo multipart/form-data no es válido.",
            details=[{"field": "file", "issue": "malformed_multipart"}],
        ) from exc


def _close_files(form) -> None:
    for _, value in form.multi_items():
        if isinstance(value, UploadFile):
            try:
                value.file.close()
            except OSError:
                pass


async def read_upload(request: Request, settings: Settings) -> MultipartUpload:
    """Pasos 3 a 5: tipo de petición, campo único y tamaño máximo."""
    _require_multipart(request)
    form = await _parse_form(request, settings)
    try:
        file_items = [(name, value) for name, value in form.multi_items() if name == "file"]
        if not file_items:
            raise ApiError(
                ErrorCode.VALIDATION_ERROR,
                details=[{"field": "file", "issue": "missing"}],
            )
        if len(file_items) > 1:
            raise ApiError(
                ErrorCode.VALIDATION_ERROR,
                details=[{"field": "file", "issue": "must_be_single_file"}],
            )
        if not isinstance(file_items[0][1], UploadFile):
            raise ApiError(
                ErrorCode.VALIDATION_ERROR,
                details=[{"field": "file", "issue": "must_be_file"}],
            )
        upload = file_items[0][1]
        note = _read_note(form)
        data = await upload.read()
    finally:
        _close_files(form)

    validate_size(len(data), settings)
    if not data:
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            details=[{"field": "file", "issue": "empty_file"}],
        )
    return MultipartUpload(
        filename=sanitize_filename(upload.filename),
        declared_content_type=upload.content_type,
        data=data,
        note=note,
    )


def validate_size(size_bytes: int, settings: Settings) -> None:
    """Paso 5: tamaño <= STEGO_MAX_UPLOAD_BYTES."""
    if size_bytes > settings.stego_max_upload_bytes:
        raise ApiError(
            ErrorCode.PAYLOAD_TOO_LARGE,
            details=[{"field": "file", "issue": "size_exceeds_limit"}],
        )


def _read_note(form) -> str | None:
    notes = [value for name, value in form.multi_items() if name == "note"]
    if not notes:
        return None
    if len(notes) > 1:
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            details=[{"field": "note", "issue": "must_be_single"}],
        )
    note = notes[0]
    if not isinstance(note, str):
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            details=[{"field": "note", "issue": "must_be_text"}],
        )
    if len(note) > NOTE_MAX_LENGTH:
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            details=[{"field": "note", "issue": "too_long"}],
        )
    return note


def sanitize_filename(raw: str | None) -> str:
    """Nombre original saneado: sin rutas, sin caracteres de control, <= 255."""
    candidate = (raw or "").replace("\\", "/").rsplit("/", 1)[-1]
    candidate = unicodedata.normalize("NFC", candidate)
    candidate = "".join(character for character in candidate if unicodedata.category(character)[0] != "C")
    candidate = candidate.strip().strip(".")
    if not candidate:
        return "archivo"
    if len(candidate) <= 255:
        return candidate
    stem, dot, extension = candidate.rpartition(".")
    if dot and 0 < len(extension) <= 10:
        return stem[: 255 - len(extension) - 1] + "." + extension
    return candidate[:255]


def _extension(filename: str) -> str:
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].strip().lower()


def _signature_matches(data: bytes, content_type: str) -> bool:
    if content_type == "image/png":
        return data.startswith(PNG_MAGIC)
    if content_type == "image/bmp":
        return data.startswith(BMP_MAGIC)
    return False


def _png_container_is_intact(data: bytes) -> bool:
    """Recorre los chunks hasta IEND y exige que el archivo termine ahí."""
    if not data.startswith(PNG_MAGIC):
        return False
    position = len(PNG_MAGIC)
    while position + 12 <= len(data):
        length = int.from_bytes(data[position : position + 4], "big")
        chunk_type = data[position + 4 : position + 8]
        position += 12 + length
        if position > len(data):
            return False
        if chunk_type == b"IEND":
            return position == len(data)
    return False


def _bmp_container_is_intact(data: bytes) -> bool:
    if len(data) < 14 or not data.startswith(BMP_MAGIC):
        return False
    declared_size = int.from_bytes(data[2:6], "little")
    return declared_size in (0, len(data))


def _container_is_intact(data: bytes, content_type: str) -> bool:
    if content_type == "image/png":
        return _png_container_is_intact(data)
    if content_type == "image/bmp":
        return _bmp_container_is_intact(data)
    return False


def _decode(data: bytes, content_type: str, settings: Settings) -> tuple[int, int, Image.Image]:
    """Paso 9 (decodifica) y paso 10 (límites de procesamiento)."""
    expected_format = EXPECTED_FORMATS[content_type]
    try:
        image = Image.open(io.BytesIO(data))
    except Image.DecompressionBombError as exc:
        raise ApiError(
            ErrorCode.PAYLOAD_TOO_LARGE,
            details=[{"field": "file", "issue": "dimension_limit"}],
        ) from exc
    except Image.UnidentifiedImageError as exc:
        raise ApiError(
            ErrorCode.IMAGE_UNPROCESSABLE,
            details=[{"field": "file", "issue": "not_a_decodable_image"}],
        ) from exc
    except (OSError, ValueError, SyntaxError) as exc:
        raise ApiError(
            ErrorCode.IMAGE_UNPROCESSABLE,
            details=[{"field": "file", "issue": "corrupt_image"}],
        ) from exc

    if image.format != expected_format:
        image.close()
        raise ApiError(
            ErrorCode.IMAGE_UNPROCESSABLE,
            message="El archivo no decodifica como el tipo declarado.",
            details=[{"field": "file", "issue": "format_mismatch"}],
        )

    width, height = image.size
    if width <= 0 or height <= 0:
        image.close()
        raise ApiError(
            ErrorCode.IMAGE_UNPROCESSABLE,
            details=[{"field": "file", "issue": "empty_image"}],
        )

    too_large = (
        width > settings.stego_max_image_dimension
        or height > settings.stego_max_image_dimension
        or width * height > settings.stego_max_image_pixels
    )
    if too_large:
        # Se comprueba la integridad del contenedor (barato) antes de negarse a
        # decodificar: así un archivo corrupto sigue siendo 422 y no se asignan
        # cientos de MB decodificando una imagen que de todos modos se rechaza.
        intact = _container_is_intact(data, content_type)
        image.close()
        if not intact:
            raise ApiError(
                ErrorCode.IMAGE_UNPROCESSABLE,
                details=[{"field": "file", "issue": "corrupt_image"}],
            )
        raise ApiError(
            ErrorCode.PAYLOAD_TOO_LARGE,
            details=[{"field": "file", "issue": "dimension_limit"}],
        )

    try:
        image.load()
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
        image.close()
        raise ApiError(
            ErrorCode.IMAGE_UNPROCESSABLE,
            details=[{"field": "file", "issue": "truncated_or_corrupt"}],
        ) from exc

    if not _container_is_intact(data, content_type):
        image.close()
        raise ApiError(
            ErrorCode.IMAGE_UNPROCESSABLE,
            message="El archivo contiene datos fuera del contenedor declarado.",
            details=[{"field": "file", "issue": "trailing_data"}],
        )

    return width, height, image


def validate_upload(upload: MultipartUpload, settings: Settings) -> ValidatedImage:
    """Pasos 6 a 10: extensión, tipo, firma, decodificación y límites."""
    extension = _extension(upload.filename)
    if extension not in settings.allowed_extensions:
        raise ApiError(
            ErrorCode.UNSUPPORTED_MEDIA_TYPE,
            message="La extensión del archivo no está permitida.",
            details=[{"field": "file", "issue": "extension_not_allowed"}],
        )

    content_type = settings.canonical_content_type(upload.declared_content_type)
    if content_type is None:
        raise ApiError(
            ErrorCode.UNSUPPORTED_MEDIA_TYPE,
            message="El tipo declarado del archivo no está permitido.",
            details=[{"field": "file", "issue": "content_type_not_allowed"}],
        )

    if not _signature_matches(upload.data, content_type):
        raise ApiError(
            ErrorCode.FILE_SIGNATURE_MISMATCH,
            details=[{"field": "file", "issue": "signature_mismatch"}],
        )

    width, height, image = _decode(upload.data, content_type, settings)
    return ValidatedImage(
        filename=upload.filename,
        declared_content_type=upload.declared_content_type or "",
        content_type=content_type,
        data=upload.data,
        size_bytes=len(upload.data),
        sha256=hashlib.sha256(upload.data).hexdigest(),
        width=width,
        height=height,
        image=image,
    )


def store_quarantined(data: bytes, content_type: str, settings: Settings) -> str:
    """Guarda el archivo con nombre aleatorio, extensión canónica y permisos 0640."""
    directory: Path = settings.quarantine_path
    extension = CANONICAL_EXTENSIONS[content_type]
    target = directory / f"{uuid.uuid4().hex}.{extension}"
    try:
        directory.mkdir(mode=0o750, parents=True, exist_ok=True)
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
        except OSError:
            target.unlink(missing_ok=True)
            raise
        os.chmod(target, 0o640)
    except OSError as exc:
        logger.error(
            "quarantine_write_failed",
            extra={"fields": {"error_type": type(exc).__name__, "error_message": str(exc)}},
        )
        raise ApiError(ErrorCode.INTERNAL_ERROR) from exc
    return str(target)
