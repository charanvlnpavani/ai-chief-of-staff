import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from app.core.schemas import APIModel
from app.core.time import is_valid_timezone

ConsentCategory = Literal["ai_processing", "ai_health", "ai_finance", "ai_email_content"]
CONSENT_POLICY_VERSION = "2026-11-17"


class UserOut(APIModel):
    id: uuid.UUID
    email: str
    display_name: str
    timezone: str
    locale: str
    currency: str
    created_at: datetime


class UserUpdate(APIModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    timezone: str | None = None
    locale: str | None = Field(default=None, pattern=r"^[a-z]{2}(-[A-Z]{2})?$")
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")

    @field_validator("timezone")
    @classmethod
    def _valid_timezone(cls, value: str | None) -> str | None:
        if value is not None and not is_valid_timezone(value):
            raise ValueError("must be an IANA time zone such as Asia/Kolkata")
        return value


class AIPreferences(APIModel):
    monthly_budget_usd: float = Field(default=25.0, ge=0, le=1000)


class Preferences(APIModel):
    theme: Literal["system", "light", "dark"] = "system"
    week_starts_on: Literal[1, 7] = 1
    daily_learning_goal_minutes: int = Field(default=120, ge=0, le=1440)
    privacy_mode_default: bool = False
    ai: AIPreferences = Field(default_factory=AIPreferences)


class AIPreferencesUpdate(APIModel):
    monthly_budget_usd: float | None = Field(default=None, ge=0, le=1000)


class PreferencesUpdate(APIModel):
    theme: Literal["system", "light", "dark"] | None = None
    week_starts_on: Literal[1, 7] | None = None
    daily_learning_goal_minutes: int | None = Field(default=None, ge=0, le=1440)
    privacy_mode_default: bool | None = None
    ai: AIPreferencesUpdate | None = None


class SettingsOut(APIModel):
    preferences: Preferences
    version: int


class MeOut(APIModel):
    user: UserOut
    preferences: Preferences


class ConsentOut(APIModel):
    category: ConsentCategory
    status: Literal["granted", "revoked", "not_set"]
    policy_version: str | None = None
    granted_at: datetime | None = None
    revoked_at: datetime | None = None


class ConsentUpdate(APIModel):
    granted: bool


class SessionOut(APIModel):
    id: uuid.UUID
    client: str
    device_label: str | None
    user_agent: str | None
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    current: bool = False


class AuthConfigOut(APIModel):
    google_enabled: bool
    dev_login_enabled: bool


class DevLoginIn(APIModel):
    email: str | None = Field(default=None, max_length=254)
