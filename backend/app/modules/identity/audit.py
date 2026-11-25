"""Audit trail writer. Callers add the row inside their transaction; it commits with their work."""

import uuid
from typing import Any, Literal

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import request_id_var
from app.core.ratelimit import client_ip
from app.core.security import ip_prefix
from app.modules.identity.models import AuditLog

ActorType = Literal["user", "ai", "system", "integration"]


def record_audit(
    session: AsyncSession,
    *,
    user_id: uuid.UUID | None,
    action: str,
    actor_type: ActorType = "user",
    actor_id: str | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
    request: Request | None = None,
) -> None:
    session.add(
        AuditLog(
            user_id=user_id,
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            request_id=request_id_var.get(),
            ip_prefix=ip_prefix(client_ip(request)) if request else None,
            details=details or {},
        )
    )
