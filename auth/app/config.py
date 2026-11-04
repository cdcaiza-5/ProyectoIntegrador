from functools import lru_cache
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    auth_http_port: int = 8080

    db_host: str = "db"
    db_port: int = 5432
    db_name: str = "auth"
    db_user: str = "auth_app"
    db_password: str = ""

    auth_jwt_private_key_path: str = "/run/secrets/jwt_private.pem"
    auth_jwt_public_key_path: str = "/run/secrets/jwt_public.pem"
    auth_jwt_kid: str = "auth-2026-11"
    auth_jwt_issuer: str = "auth-service"
    auth_access_token_ttl_seconds: int = 900
    auth_audiences: str = "auth-api,stego-api"

    auth_service_token_ttl_seconds: int = 300
    auth_service_client_id: str = "stego"
    auth_service_client_secret: str = ""
    auth_authz_decision_ttl_seconds: int = 30

    auth_login_rate_limit_per_minute: int = 5
    auth_log_level: str = "info"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.db_user}:{quote_plus(self.db_password)}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def audiences(self) -> list[str]:
        return [item.strip() for item in self.auth_audiences.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
