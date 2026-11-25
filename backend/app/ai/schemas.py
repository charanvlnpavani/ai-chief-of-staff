import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

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


class AIStatusOut(APIModel):
    enabled: bool
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
