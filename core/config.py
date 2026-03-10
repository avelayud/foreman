"""
core/config.py
Centralized configuration and environment variable management.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _env_trim(name: str, default: str = "") -> str:
    value = os.getenv(name, default)
    if isinstance(value, str):
        return value.strip()
    return value


class Config:
    # AI
    ANTHROPIC_API_KEY: str = _env_trim("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL: str = "claude-sonnet-4-20250514"

    # Email
    SENDGRID_API_KEY: str = _env_trim("SENDGRID_API_KEY", "")
    SENDGRID_FROM_EMAIL: str = _env_trim("SENDGRID_FROM_EMAIL", "")

    # SMS
    TWILIO_ACCOUNT_SID: str = _env_trim("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str = _env_trim("TWILIO_AUTH_TOKEN", "")
    TWILIO_FROM_NUMBER: str = _env_trim("TWILIO_FROM_NUMBER", "")

    # Google
    GOOGLE_CLIENT_ID: str = _env_trim("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = _env_trim("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI: str = _env_trim("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback")

    # Database
    DATABASE_URL: str = _env_trim("DATABASE_URL", "sqlite:///./foreman.db")

    # App
    APP_ENV: str = _env_trim("APP_ENV", "development")
    APP_PORT: int = int(_env_trim("APP_PORT", "8000"))
    LOG_LEVEL: str = _env_trim("LOG_LEVEL", "INFO")

    # Agent behavior
    REACTIVATION_THRESHOLD_DAYS: int = int(_env_trim("REACTIVATION_THRESHOLD_DAYS", "365"))
    DAILY_OUTREACH_LIMIT: int = int(_env_trim("DAILY_OUTREACH_LIMIT", "20"))
    DRY_RUN: bool = _env_trim("DRY_RUN", "true").lower() == "true"

    @classmethod
    def validate(cls):
        """Validate required keys are present. Call at startup."""
        required = ["ANTHROPIC_API_KEY"]
        missing = [k for k in required if not getattr(cls, k)]
        if missing:
            raise EnvironmentError(f"Missing required environment variables: {missing}")

    @classmethod
    def is_development(cls):
        return cls.APP_ENV == "development"


config = Config()
