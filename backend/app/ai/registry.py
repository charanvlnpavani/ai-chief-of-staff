"""Tool registry and permission model for the AI Chief of Staff.

Every capability the model can use is a registered, typed tool. The backend decides per
request which tools are offered; the model can never reach the database, files, accounts
or credentials directly.

Levels
  1 READ            read the user's records (minimised output)              -> runs, audited
  2 SUGGEST         plans and drafts in the reply; never changes data         -> runs, audited
  3 INTERNAL_WRITE  change Personal OS data          -> creates an approval request (Release 6)
  4 EXTERNAL_WRITE  act on Google, YouTube, ...      -> approval + fresh sign-in (Release 6)
  Restricted actions (payments, transfers, credentials, deletions, auto-apply) are never
  registered, so no code path exists for them.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from enum import IntEnum
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.schemas import ConsentCategory


class Level(IntEnum):
    READ = 1
    SUGGEST = 2
    INTERNAL_WRITE = 3
    EXTERNAL_WRITE = 4


@dataclass(frozen=True, slots=True)
class ToolContext:
    session: AsyncSession
    user_id: uuid.UUID
    timezone: str
    today: date


ToolFn = Callable[[ToolContext, Any], Awaitable[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    fn: ToolFn
    level: Level = Level.READ
    scopes: tuple[str, ...] = ()
    consent: ConsentCategory | None = "ai_processing"
    version: str = "1"
    timeout_s: float = 10.0

    def definition(self) -> dict[str, Any]:
        schema = self.input_model.model_json_schema()
        schema.pop("title", None)
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": schema,
            # Stream tool inputs as generated. The server then skips input validation,
            # which is fine: every input is validated against `input_model` before running.
            "eager_input_streaming": True,
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool {tool.name!r} registered twice")
        if tool.level >= Level.INTERNAL_WRITE:
            raise ValueError("write tools require the approval workflow (planned for Release 6)")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all(self) -> list[Tool]:
        # Sorted, so the tool list (part of the cached prompt prefix) is byte-stable.
        return [self._tools[name] for name in sorted(self._tools)]

    def allowed(self, *, ceiling: Level, granted_consents: set[str]) -> list[Tool]:
        return [
            t
            for t in self.all()
            if t.level <= ceiling and (t.consent is None or t.consent in granted_consents)
        ]


registry = ToolRegistry()


def tool(
    *,
    name: str,
    description: str,
    input_model: type[BaseModel],
    level: Level = Level.READ,
    scopes: tuple[str, ...] = (),
    consent: ConsentCategory | None = "ai_processing",
    version: str = "1",
    timeout_s: float = 10.0,
) -> Callable[[ToolFn], ToolFn]:
    def decorate(fn: ToolFn) -> ToolFn:
        registry.register(
            Tool(
                name=name,
                description=description,
                input_model=input_model,
                fn=fn,
                level=level,
                scopes=scopes,
                consent=consent,
                version=version,
                timeout_s=timeout_s,
            )
        )
        return fn

    return decorate
