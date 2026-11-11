from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+psycopg://music:music_local_only@localhost:5432/music_room"
    jwt_secret: SecretStr
    jwt_issuer: str = "music-room"
    jwt_audience: str = "music-room-mobile"
    access_seconds: int = Field(default=900, ge=60, le=3600)
    refresh_days: int = Field(default=30, ge=1, le=90)
    cors_origins: list[str] = []
    mail_directory: str = ".dev-mail"
    email_link_base: str = "http://localhost:8000"
    google_web_return_url: str = "http://localhost:8081/"
    google_client_id: str = ""
    google_client_secret: SecretStr = SecretStr("")
    google_redirect_uri: str = "http://localhost:8000/api/v1/auth/google/callback"
    music_rate_limit: int = Field(default=300, ge=1)
    rate_limit: int = Field(default=20, ge=1)
    rate_window_seconds: int = Field(default=300, ge=1)

    @property
    def browser_origins(self) -> list[str]:
        origins = list(self.cors_origins)
        if self.app_env == "development":
            origins.extend(
                f"http://{host}:{port}"
                for host in ("localhost", "127.0.0.1")
                for port in range(8081, 8085)
            )
        return list(dict.fromkeys(origins))

    @model_validator(mode="after")
    def secure_settings(self):
        if len(self.jwt_secret.get_secret_value()) < 32:
            raise ValueError("JWT_SECRET must contain at least 32 characters")
        if self.app_env == "production":
            if self.google_client_id and not self.google_web_return_url.startswith("https://"):
                raise ValueError("Production Google web return requires HTTPS")
            if not self.email_link_base.startswith("https://"):
                raise ValueError("Production email links require HTTPS")
            if self.google_client_id and not self.google_redirect_uri.startswith("https://"):
                raise ValueError("Production OAuth redirect requires HTTPS")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
