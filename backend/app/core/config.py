from functools import lru_cache
from typing import Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, read from environment variables and backend/.env."""

    # Empty values in .env (e.g. `OPENAI_MODEL=`) fall back to the defaults below.
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    app_env: str = "development"
    # The assistant's display name. Change it here (or via APP_NAME) to rename it everywhere.
    app_name: str = "Assistant"
    # Who the assistant is talking to, used in the system prompt.
    owner_name: str = "the owner"
    # "default" (warm, polite) or "friend" (close-friend talk: slang and swearing).
    assistant_style: str = "default"

    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-5.4-mini"

    # Voice engine: "live" (GPT-Live: full-duplex voice that delegates real work to the
    # brain) or "realtime" (one realtime model listens, thinks and acts itself).
    voice_engine: str = "live"
    live_model: str = "gpt-live-1"
    live_voice: str = "cedar"

    # Voice (OpenAI Realtime). The full model hears and speaks Azerbaijani far better;
    # gpt-realtime-2.1-mini is ~3x cheaper per audio minute.
    realtime_model: str = "gpt-realtime-2.1"
    realtime_voice: str = "marin"
    # The larger transcription model is noticeably better at Azerbaijani and at names.
    realtime_transcribe_model: str = "gpt-live-transcribe"
    # Spoken language hint for transcription, e.g. "az", "en", "tr".
    voice_language: str = "az"

    # Native Azerbaijani speech (Azure Speech). When the key is set, voice answers are
    # spoken by this voice instead of the realtime model's own, which has a foreign accent.
    azure_speech_key: SecretStr | None = None
    azure_speech_region: str = "westeurope"
    # az-AZ-BabekNeural (male) or az-AZ-BanuNeural (female).
    azure_tts_voice: str = "az-AZ-BabekNeural"

    # Obsidian vault for long-term memory and conversation logs. Empty disables it.
    obsidian_vault_path: str | None = None

    # When true, high-risk actions (shell, Terminal, AppleScript) run without asking,
    # except commands that look destructive (rm -r, sudo, ...), which still need a confirm.
    full_autonomy: bool = False

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/personal_ai"

    secret_key: SecretStr | None = None
    # When set, device agents must present this token to connect.
    agent_token: SecretStr | None = None

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
