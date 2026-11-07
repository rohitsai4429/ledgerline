from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "LedgerLine API"
    app_env: str = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    database_url: str = "postgresql+psycopg://localhost:5433/ledgerline"
    cors_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    jwt_secret_key: SecretStr = Field(min_length=32)
    jwt_algorithm: Literal["HS256"] = "HS256"
    jwt_access_token_minutes: int = Field(default=30, gt=0, le=1440)

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("jwt_secret_key")
    @classmethod
    def reject_example_jwt_secret(cls, value: SecretStr) -> SecretStr:
        if value.get_secret_value().startswith("CHANGE_ME_"):
            raise ValueError("JWT_SECRET_KEY must be replaced with a generated secret")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
