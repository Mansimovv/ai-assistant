from functools import lru_cache
from typing import Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, read from environment variables and backend/.env."""

    # Empty values in .env (e.g. `OPENAI_MODEL=`) fall back to the defaults below.
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    app_env: str = "development"

    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-5.4-mini"

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/personal_ai"

    secret_key: SecretStr | None = None

    # Browser origins allowed to call the API (the web dashboard).
    cors_origins: list[str] = ["http://localhost:3000"]

    @model_validator(mode="after")
    def _require_secret_key_in_production(self) -> Self:
        if self.app_env == "production" and self.secret_key is None:
            raise ValueError("SECRET_KEY must be set when APP_ENV=production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
