import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field, SecretStr

from app.core.schemas import APIModel


class ConversationIn(APIModel):
    title: str | None = Field(default=None, max_length=120)


class ConversationOut(APIModel):
    id: uuid.UUID
    title: str | None
    last_message_at: datetime
    created_at: datetime


class ToolCallOut(APIModel):
    name: str
    ok: bool


class DisplayMessage(APIModel):
    """A user-visible message. Tool-result turns and thinking blocks are not shown."""

    id: uuid.UUID
    role: Literal["user", "assistant"]
    text: str
    tool_calls: list[ToolCallOut] = []
    created_at: datetime


class ConversationDetailOut(APIModel):
    conversation: ConversationOut
    messages: list[DisplayMessage]


class MessageIn(APIModel):
    content: str = Field(min_length=1, max_length=4000)


class ToolInfoOut(APIModel):
    name: str
    description: str
    level: int
    consent: str | None
    available: bool


ProviderIdOut = Literal["anthropic", "openai", "gemini", "openrouter", "groq", "ollama", "custom"]


class ProviderOut(APIModel):
    id: ProviderIdOut
    name: str
    kind: Literal["anthropic", "openai_compatible"]
    needs_key: bool
    custom_url: bool = Field(description="You can (or must) enter the endpoint URL.")
    default_base_url: str | None
    key_url: str | None = Field(description="Where to create an API key.")
    free_note: str | None
    default_model: str | None


class ConnectionIn(APIModel):
    api_key: SecretStr | None = Field(
        default=None, description="Your API key. Never returned. Omit to keep the stored one."
    )
    base_url: str | None = Field(default=None, max_length=300)
    model: str | None = Field(default=None, max_length=120)
    activate: bool = Field(default=True, description="Use this provider for AI from now on.")


class ConnectionUpdate(APIModel):
    model: str | None = Field(default=None, max_length=120)
    active: bool | None = None


class ConnectionOut(APIModel):
    provider: ProviderIdOut
    provider_name: str
    hint: str | None = Field(description="Last four characters of your key, e.g. …wxyz.")
    base_url: str | None
    model: str | None
    active: bool
    free: bool
    verified_at: datetime


class ActiveAIOut(APIModel):
    provider: ProviderIdOut
    provider_name: str
    model: str
    source: Literal["user", "server"]
    free: bool


class ConnectionsOut(APIModel):
    mode: Literal["user", "server"] = Field(
        description="`user`: everyone brings their own key. `server`: a shared key may be used."
    )
    active: ActiveAIOut | None
    connections: list[ConnectionOut]


class ModelOut(APIModel):
    id: str
    free: bool


class AIStatusOut(APIModel):
    enabled: bool = Field(description="An AI connection is available for you.")
    key_source: Literal["user", "server"] | None = None
    provider: str | None = None
    model: str
    consent_granted: bool
    month_to_date_usd: float
    monthly_budget_usd: float
    budget_remaining_usd: float


class UsageByRoute(APIModel):
    route: str
    requests: int
    cost_usd: float
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int


class UsageOut(APIModel):
    month: str
    month_to_date_usd: float
    monthly_budget_usd: float
    by_route: list[UsageByRoute]
