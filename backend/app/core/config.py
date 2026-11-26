"""Typed application settings.

Values come from environment variables (and `backend/.env` in development).
Secrets are wrapped in `SecretStr` so they never appear in logs or reprs.
"""

from functools import lru_cache
from typing import Annotated, Literal, Self

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Environment = Literal["development", "test", "production"]
Effort = Literal["low", "medium", "high", "xhigh", "max"]
AIKeyMode = Literal["user", "server"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Environment = "development"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://localhost:5432/personal_os"

    # --- secrets -----------------------------------------------------------
    secret_key: SecretStr = SecretStr("")
    """Signs short-lived values such as the OAuth state cookie."""
    encryption_keys: SecretStr = SecretStr("")
    """Comma-separated `key_id:base64key` pairs (32-byte AES keys). The first key encrypts."""

    # --- web & sign-in ------------------------------------------------------
    web_origin: str = "http://localhost:3000"
    allowed_login_emails: Annotated[list[str], NoDecode] = []
    dev_login_enabled: bool = False
    session_idle_days: int = 14
    session_absolute_days: int = 30
    google_client_id: str = ""
    google_client_secret: SecretStr = SecretStr("")

    # --- defaults for new accounts ------------------------------------------
    default_timezone: str = "Asia/Kolkata"
    default_currency: str = "INR"

    # --- AI Chief of Staff --------------------------------------------------
    ai_key_mode: AIKeyMode = "user"
    """`user`: every person adds their own Anthropic key in Settings (required in production).
    `server`: a single-user self-host may use ANTHROPIC_API_KEY when no personal key is set."""
    anthropic_api_key: SecretStr = SecretStr("")
    ai_allow_private_endpoints: bool | None = None
    """Let users point a provider at localhost or a private network (e.g. Ollama on this
    machine). Defaults to on in development, off in production (it would let anyone make the
    server call internal addresses). Set true only for a single-user self-host."""
    ai_model_chat: str = "claude-opus-5-5"
    ai_effort_chat: Effort = "medium"
    ai_max_tokens: int = 16000
    ai_max_tool_iterations: int = 8
    ai_default_monthly_budget_usd: float = 25.0
    ai_refusal_fallback: bool = True
    ai_conversation_retention_days: int = 90

    # --- learning references --------------------------------------------------
    roadmap_sh_content_dir: str = ""
    """Optional path to a local clone of github.com/nilbuild/developer-roadmap. Its licence
    allows personal use only, so the content is read from this machine at request time and
    shown only to its user: never stored, committed, published or sent to an AI provider."""

    @field_validator("allowed_login_emails", mode="before")
    @classmethod
    def _split_emails(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip().lower() for item in value.split(",") if item.strip()]
        if isinstance(value, list):
            return [str(item).strip().lower() for item in value]
        return value

    @model_validator(mode="after")
    def _require_safe_production_config(self) -> Self:
        if self.environment == "production":
            if len(self.secret_key.get_secret_value()) < 32:
                raise ValueError("SECRET_KEY must be at least 32 characters in production")
            if not self.encryption_keys.get_secret_value():
                raise ValueError("ENCRYPTION_KEYS is required in production")
            if self.dev_login_enabled:
                raise ValueError("DEV_LOGIN_ENABLED must be false in production")
            if self.ai_key_mode != "user":
                raise ValueError(
                    "AI_KEY_MODE must be 'user' in production: every user brings their own key"
                )
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def session_cookie_name(self) -> str:
        # The __Host- prefix forces Secure, Path=/ and no Domain, which needs HTTPS.
        return "__Host-pos_session" if self.is_production else "pos_session"

    @property
    def cookie_secure(self) -> bool:
        return self.is_production

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret.get_secret_value())

    @property
    def dev_login_allowed(self) -> bool:
        return self.dev_login_enabled and not self.is_production

    @property
    def private_endpoints_allowed(self) -> bool:
        if self.ai_allow_private_endpoints is not None:
            return self.ai_allow_private_endpoints
        return not self.is_production

    @property
    def server_api_key(self) -> str | None:
        """The shared ANTHROPIC_API_KEY, only when AI_KEY_MODE allows sharing it."""
        key = self.anthropic_api_key.get_secret_value()
        return key if key and self.ai_key_mode == "server" else None


@lru_cache
def get_settings() -> Settings:
    return Settings()
