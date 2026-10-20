from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Change only this line, then restart the backend: "minimax" or "luna".
SAARTHI_MODEL: Literal["minimax", "luna"] = "minimax"
MODEL_PRESETS = {
    "minimax": {
        "model": "openrouter/minimax/minimax-m3.1-flash:free",
        "provider": None,
        "effort": "provider_default",
    },
    "luna": {"model": "openrouter/openai/gpt-6-luna", "provider": "openai", "effort": "medium"},
}
_ACTIVE_MODEL = MODEL_PRESETS[SAARTHI_MODEL]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+psycopg://saarthi:saarthi@localhost:5432/saarthi"
    app_origin: str = "http://localhost:8000"
    openrouter_api_key: str = ""
    agent_model: str = _ACTIVE_MODEL["model"]
    agent_provider: str | None = Field(
        default=_ACTIVE_MODEL["provider"], pattern=r"^[a-z0-9][a-z0-9_/-]{0,99}$"
    )
    agent_timeout_seconds: int = 60
    agent_max_output_tokens: int = Field(default=4096, ge=256, le=32768)
    agent_reasoning_effort: Literal[
        "none", "low", "medium", "high", "xhigh", "max", "provider_default"
    ] = _ACTIVE_MODEL["effort"]
    session_days: int = 7

    @model_validator(mode="after")
    def safe_configuration(self):
        if self.environment == "production":
            raise ValueError(
                "Mock OTP authentication is development/test only; replace it before deployment."
            )
        origin = urlparse(self.app_origin)
        if (
            origin.scheme not in ("http", "https")
            or not origin.hostname
            or origin.path
            or origin.query
            or origin.fragment
            or origin.username
        ):
            raise ValueError("APP_ORIGIN must be an origin without a path.")
        if origin.scheme == "http" and origin.hostname not in (
            "localhost",
            "127.0.0.1",
            "::1",
            "testserver",
        ):
            raise ValueError("HTTP cookies are allowed only on localhost/testserver.")
        if not self.database_url.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must use postgresql+psycopg://")
        if not 1 <= self.agent_timeout_seconds <= 180 or not 1 <= self.session_days <= 30:
            raise ValueError("Invalid timeout or session lifetime.")
        return self

    @property
    def secure_cookie(self):
        return self.app_origin.startswith("https://")
