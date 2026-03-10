"""
core/config.py
Centralized configuration and environment variable management.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # AI
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL: str = "claude-sonnet-4-20250514"

    # Email
    SENDGRID_API_KEY: str = os.getenv("SENDGRID_API_KEY", "")
    SENDGRID_FROM_EMAIL: str = os.getenv("SENDGRID_FROM_EMAIL", "")

    # SMS
    TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_FROM_NUMBER: str = os.getenv("TWILIO_FROM_NUMBER", "")

    # Google
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI: str = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback")

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./foreman.db")

    # App
    APP_ENV: str = os.getenv("APP_ENV", "development")
    APP_PORT: int = int(os.getenv("APP_PORT", "8000"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Agent behavior
    REACTIVATION_THRESHOLD_DAYS: int = int(os.getenv("REACTIVATION_THRESHOLD_DAYS", "365"))
    DAILY_OUTREACH_LIMIT: int = int(os.getenv("DAILY_OUTREACH_LIMIT", "20"))
    DRY_RUN: bool = os.getenv("DRY_RUN", "true").lower() == "true"

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
