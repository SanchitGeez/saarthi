from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values, load_dotenv
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]

# Local development may reuse model and speech credentials from the sibling
# MindLap project. Deliberately exclude DATABASE_URL and every unrelated key.
load_dotenv(ROOT / ".env", override=False)
if os.getenv("APP_ENV", "development") == "development":
    sibling_env = ROOT.parent / "mindlap" / ".env"
    if sibling_env.is_file():
        allowed = {
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "ELEVEN_LABS",
            "ELEVEN_LABS_API_KEY",
            "ELEVEN_LABS_VOICE_ID",
        }
        for key, value in dotenv_values(sibling_env).items():
            if key in allowed and value and not os.getenv(key):
                os.environ[key] = value

# The root example may define the canonical key as an empty string while the
# sibling development environment uses the older ELEVEN_LABS name.
if not os.getenv("ELEVEN_LABS_API_KEY") and os.getenv("ELEVEN_LABS"):
    os.environ["ELEVEN_LABS_API_KEY"] = os.environ["ELEVEN_LABS"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    app_env: str = "development"
    app_name: str = "saarthi"
    database_url: str = Field(
        default="postgresql+asyncpg://saarthi:saarthi@localhost:54330/saarthi",
        validation_alias="SAARTHI_DATABASE_URL",
    )
    jwt_secret: str = "local-only-change-me-before-deploying-32chars"
    jwt_days: int = 30
    google_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    gemini_fallback_model: str = "gemini-flash-lite-latest"
    openai_api_key: str = ""
    openai_base_url: str | None = None
    openai_embedding_model: str = "text-embedding-3-small"
    eleven_labs_api_key: str = Field(
        default="", validation_alias=AliasChoices("ELEVEN_LABS_API_KEY", "ELEVEN_LABS")
    )
    eleven_labs_voice_id: str = "JBFqnCBsd6RMkjVDRZzb"
    eleven_labs_tts_model: str = "eleven_multilingual_v2"
    eleven_labs_stt_model: str = "scribe_v2"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    mobile_origins: str = "http://localhost:8081,http://localhost:19006"

    @property
    def is_development(self) -> bool:
        return self.app_env.lower() == "development"

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.mobile_origins.split(",") if origin.strip()]


settings = Settings()

if not settings.is_development and (len(settings.jwt_secret) < 32 or settings.jwt_secret.startswith(("local-only-", "replace-this-"))):
    raise RuntimeError("JWT_SECRET must contain at least 32 characters outside development.")
