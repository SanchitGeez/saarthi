from typing import Literal
from urllib.parse import urlparse

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+psycopg://saarthi:saarthi@localhost:5432/saarthi"
    app_origin: str = "http://localhost:8000"
    groq_api_key: str = ""
    agent_model: str = "groq/openai/gpt-oss-20b"
    agent_timeout_seconds: int = 60
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
