"""Configuración del servicio STEGO (contrato 7 §3).

Todos los nombres de variables son contrato. Las marcadas como obligatorias en
el contrato no tienen valor por defecto: si faltan, el proceso no arranca.
Las variables de la sección "opcional" son añadidos propios de STEGO y están
documentadas en ``.env.example`` como tales.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

CANONICAL_CONTENT_TYPES = {
    "image/png": "image/png",
    "image/bmp": "image/bmp",
    "image/x-ms-bmp": "image/bmp",
}

SUPPORTED_EXTENSIONS = frozenset({"png", "bmp"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    stego_http_port: int = Field(default=8081, gt=0, le=65535)
    api_v1_str: str = "/api/v1"

    db_host: str = "db"
    db_port: int = Field(default=5432, gt=0, le=65535)
    db_name: str = "stego"
    db_user: str = "stego_app"
    db_password: str

    stego_auth_base_url: str = "http://auth:8080"
    stego_auth_jwks_url: str = "http://auth:8080/.well-known/jwks.json"
    stego_auth_jwks_timeout_ms: int = Field(default=1500, gt=0)
    stego_service_client_id: str = "stego"
    stego_service_client_secret: str
    stego_service_token_refresh_seconds: int = Field(default=240, gt=0)
    stego_authz_timeout_ms: int = Field(default=2000, gt=0)

    stego_max_upload_bytes: int = Field(default=5 * 1024 * 1024, gt=0)
    stego_allowed_extensions: str = "png,bmp"
    stego_allowed_content_types: str = "image/png,image/bmp,image/x-ms-bmp"
    stego_max_image_dimension: int = Field(default=10000, gt=0)
    stego_max_image_pixels: int = Field(default=25_000_000, gt=0)
    stego_lsb_anomaly_threshold: float = Field(default=0.75, gt=0.0, le=1.0)

    stego_storage_quarantine_path: str = "/var/stego/quarantine"
    stego_storage_retention_days: int = Field(default=7, ge=0)
    stego_log_level: str = "info"

    # Opcionales de STEGO (no están en el contrato 7 §3; ver .env.example).
    stego_jwt_issuer: str = "auth-service"
    stego_jwt_audience: str = "stego-api"
    stego_jwt_leeway_seconds: int = Field(default=60, ge=0)
    stego_jwks_cache_seconds: int = Field(default=300, gt=0)
    stego_service_token_min_remaining_seconds: int = Field(default=60, ge=0)
    stego_min_analysis_pixels: int = Field(default=16384, ge=1)
    stego_min_palette_colors: int = Field(default=16, ge=1)

    @field_validator("api_v1_str")
    @classmethod
    def _normalise_prefix(cls, value: str) -> str:
        prefix = "/" + value.strip().strip("/")
        return "" if prefix == "/" else prefix

    @field_validator("stego_allowed_extensions", "stego_allowed_content_types")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not [part for part in value.split(",") if part.strip()]:
            raise ValueError("la lista no puede estar vacía")
        return value

    @model_validator(mode="after")
    def _check_supported_lists(self) -> "Settings":
        unknown_types = self.allowed_content_types - set(CANONICAL_CONTENT_TYPES)
        if unknown_types:
            raise ValueError(
                "STEGO_ALLOWED_CONTENT_TYPES contiene tipos sin analizador: "
                + ", ".join(sorted(unknown_types))
            )
        unknown_extensions = self.allowed_extensions - SUPPORTED_EXTENSIONS
        if unknown_extensions:
            raise ValueError(
                "STEGO_ALLOWED_EXTENSIONS contiene extensiones sin analizador: "
                + ", ".join(sorted(unknown_extensions))
            )
        return self

    @property
    def allowed_extensions(self) -> frozenset[str]:
        return frozenset(
            part.strip().lstrip(".").lower()
            for part in self.stego_allowed_extensions.split(",")
            if part.strip()
        )

    @property
    def allowed_content_types(self) -> frozenset[str]:
        return frozenset(
            part.strip().lower()
            for part in self.stego_allowed_content_types.split(",")
            if part.strip()
        )

    @property
    def database_url(self) -> str:
        user = quote(self.db_user, safe="")
        password = quote(self.db_password, safe="")
        return (
            f"postgresql+psycopg://{user}:{password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def quarantine_path(self) -> Path:
        return Path(self.stego_storage_quarantine_path)

    @property
    def jwks_timeout_seconds(self) -> float:
        return self.stego_auth_jwks_timeout_ms / 1000.0

    @property
    def authz_timeout_seconds(self) -> float:
        return self.stego_authz_timeout_ms / 1000.0

    @property
    def service_token_refresh_seconds(self) -> int:
        return self.stego_service_token_refresh_seconds

    @property
    def jwt_issuer(self) -> str:
        return self.stego_jwt_issuer

    @property
    def jwt_audience(self) -> str:
        return self.stego_jwt_audience

    def canonical_content_type(self, declared: str | None) -> str | None:
        if not declared:
            return None
        value = declared.split(";", 1)[0].strip().lower()
        if value not in self.allowed_content_types:
            return None
        return CANONICAL_CONTENT_TYPES[value]

    @property
    def service_token_url(self) -> str:
        return self.stego_auth_base_url.rstrip("/") + "/internal/service-token"

    @property
    def authorization_url(self) -> str:
        return self.stego_auth_base_url.rstrip("/") + "/internal/authorization/check"


@lru_cache
def get_settings() -> Settings:
    return Settings()
