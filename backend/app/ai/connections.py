"""Per-user AI provider connections ("bring your own key", any provider).

A user connects one or more providers (Claude, OpenAI, Gemini, OpenRouter, Groq, local
Ollama, or any OpenAI-compatible endpoint), picks a model, and marks one connection active.
Every AI call made for them uses the active connection, so usage bills to their account.
Keys are encrypted at rest (AAD binds them to the user and provider) and never returned.

AI_KEY_MODE=user (default, required in production): no connection, no AI.
AI_KEY_MODE=server: a single-user self-host may fall back to ANTHROPIC_API_KEY.
"""

import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

import anthropic
import openai
from fastapi import Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.models import AICredential
from app.ai.providers import (
    PROVIDERS,
    Kind,
    Provider,
    check_base_url,
    get_provider,
    is_free_model,
    openai_http_client,
)
from app.ai.schemas import (
    ActiveAIOut,
    ConnectionIn,
    ConnectionOut,
    ConnectionsOut,
    ConnectionUpdate,
    ModelOut,
    ProviderOut,
)
from app.core.config import Settings, get_settings
from app.core.crypto import get_keyring
from app.core.errors import BadRequest, Forbidden, NotFound, ServiceUnavailable
from app.core.time import utc_now
from app.modules.identity import service as identity_service

logger = logging.getLogger("app.ai.connections")

ANTHROPIC_KEY = re.compile(r"^sk-ant-[A-Za-z0-9_\-]{20,300}$")
GENERIC_KEY = re.compile(r"^[\x21-\x7e]{8,400}$")  # printable, no spaces
MAX_MODELS = 500

KeySource = Literal["user", "server"]


@dataclass(frozen=True, slots=True)
class Connection:
    """Everything needed to call a model for one user. Hashable, so clients can be cached."""

    provider: str
    kind: Kind
    api_key: str | None
    base_url: str | None
    model: str
    source: KeySource

    @property
    def free(self) -> bool:
        return is_free_model(self.provider, self.model)


ModelLister = Callable[[Provider, str | None, str | None], Awaitable[list[str]]]


async def list_models_live(
    provider: Provider, api_key: str | None, base_url: str | None
) -> list[str]:
    """List models with the user's key. Doubles as the key check (a free call)."""
    try:
        if provider.kind == "anthropic":
            client = anthropic.AsyncAnthropic(api_key=api_key, timeout=15.0, max_retries=1)
            try:
                page = await client.models.list(limit=100)
                return [m.id for m in page.data]
            finally:
                await client.close()
        oai = openai.AsyncOpenAI(
            api_key=api_key or "not-needed",
            base_url=base_url,
            timeout=15.0,
            max_retries=1,
            http_client=openai_http_client(allow_private=get_settings().private_endpoints_allowed),
        )
        try:
            ids: list[str] = []
            async for model in oai.models.list():
                ids.append(model.id)
                if len(ids) >= MAX_MODELS:
                    break
            return sorted(ids)
        finally:
            await oai.close()
    except (
        anthropic.AuthenticationError,
        anthropic.PermissionDeniedError,
        openai.AuthenticationError,
        openai.PermissionDeniedError,
    ) as exc:
        raise BadRequest(f"{provider.name} rejected this API key.", code="ai_key_invalid") from exc
    except (anthropic.RateLimitError, openai.RateLimitError):
        return []  # rate limited means the key works; type the model name instead
    except openai.NotFoundError:
        return []  # some endpoints have no model list; type the model name instead
    except (anthropic.APIStatusError, openai.APIStatusError) as exc:
        logger.warning(
            "ai_models_status", extra={"provider": provider.id, "status": exc.status_code}
        )
        raise ServiceUnavailable(
            f"{provider.name} could not be checked right now. Try again.", code="ai_key_unverified"
        ) from exc
    except (anthropic.APIConnectionError, openai.APIConnectionError) as exc:
        hint = " Is Ollama running?" if provider.id == "ollama" else ""
        raise ServiceUnavailable(
            f"Could not reach {provider.name}.{hint}", code="ai_endpoint_unreachable"
        ) from exc


def get_model_lister() -> ModelLister:
    """Dependency so tests can replace the network calls."""
    return list_models_live


# ------------------------------------------------------------------ helpers


def _aad(user_id: uuid.UUID, provider: str) -> bytes:
    # Anthropic keys saved before multi-provider support used this same layout.
    return f"ai-credential:{provider}:{user_id}".encode()


def _hint(key: str) -> str:
    return f"…{key[-4:]}"


def _check_key_format(provider: Provider, key: str) -> None:
    pattern = ANTHROPIC_KEY if provider.id == "anthropic" else GENERIC_KEY
    if not pattern.fullmatch(key):
        expected = " (it starts with sk-ant-)" if provider.id == "anthropic" else ""
        raise BadRequest(
            f"That does not look like a {provider.name} API key{expected}.", code="ai_key_format"
        )


async def _rows(session: AsyncSession, user_id: uuid.UUID) -> list[AICredential]:
    return list(
        await session.scalars(
            select(AICredential)
            .where(AICredential.user_id == user_id)
            .order_by(AICredential.created_at)
        )
    )


async def _row(session: AsyncSession, user_id: uuid.UUID, provider: str) -> AICredential | None:
    return await session.scalar(
        select(AICredential).where(
            AICredential.user_id == user_id, AICredential.provider == provider
        )
    )


def _decrypt(row: AICredential) -> str | None:
    if row.key_enc is None:
        return None
    return get_keyring().decrypt(row.key_enc, aad=_aad(row.user_id, row.provider)).decode()


def _base_url(provider: Provider, row: AICredential) -> str | None:
    return row.base_url or provider.base_url


async def _activate(session: AsyncSession, user_id: uuid.UUID, row: AICredential) -> None:
    if row.model is None:
        raise BadRequest("Pick a model before using this provider.", code="ai_model_required")
    await session.execute(
        update(AICredential)
        .where(AICredential.user_id == user_id, AICredential.id != row.id)
        .values(is_active=False)
    )
    await session.flush()
    row.is_active = True


# ------------------------------------------------------------------ resolution


async def resolve_connection(
    session: AsyncSession, user_id: uuid.UUID, settings: Settings
) -> Connection | None:
    """The connection to use for this user's AI calls, or None if AI is unavailable."""
    row = await session.scalar(
        select(AICredential).where(AICredential.user_id == user_id, AICredential.is_active)
    )
    if row is not None and row.model:
        provider = PROVIDERS[row.provider]
        return Connection(
            provider=row.provider,
            kind=provider.kind,
            api_key=_decrypt(row),
            base_url=_base_url(provider, row),
            model=row.model,
            source="user",
        )
    if settings.server_api_key:
        return Connection(
            provider="anthropic",
            kind="anthropic",
            api_key=settings.server_api_key,
            base_url=None,
            model=settings.ai_model_chat,
            source="server",
        )
    return None


async def require_connection(
    session: AsyncSession, user_id: uuid.UUID, settings: Settings
) -> Connection:
    connection = await resolve_connection(session, user_id, settings)
    if connection is None:
        raise Forbidden(
            "Connect an AI provider in Settings (your own API key, or local Ollama) to use AI "
            "features.",
            code="ai_key_required",
        )
    return connection


# ------------------------------------------------------------------ read


def list_providers() -> list[ProviderOut]:
    return [
        ProviderOut(
            id=p.id,
            name=p.name,
            kind=p.kind,
            needs_key=p.needs_key,
            custom_url=p.custom_url,
            default_base_url=p.base_url,
            key_url=p.key_url,
            free_note=p.free_note,
            default_model=p.default_model,
        )
        for p in PROVIDERS.values()
    ]


async def overview(session: AsyncSession, user_id: uuid.UUID, settings: Settings) -> ConnectionsOut:
    rows = await _rows(session, user_id)
    active = await resolve_connection(session, user_id, settings)
    return ConnectionsOut(
        mode=settings.ai_key_mode,
        active=(
            ActiveAIOut(
                provider=active.provider,
                provider_name=PROVIDERS[active.provider].name,
                model=active.model,
                source=active.source,
                free=active.free,
            )
            if active
            else None
        ),
        connections=[
            ConnectionOut(
                provider=r.provider,
                provider_name=PROVIDERS[r.provider].name,
                hint=r.key_hint,
                base_url=r.base_url,
                model=r.model,
                active=r.is_active,
                free=bool(r.model) and is_free_model(r.provider, r.model or ""),
                verified_at=r.verified_at,
            )
            for r in rows
        ],
    )


async def available_models(
    session: AsyncSession, user_id: uuid.UUID, provider_id: str, *, lister: ModelLister
) -> list[ModelOut]:
    provider = get_provider(provider_id)
    row = await _row(session, user_id, provider_id)
    if row is None:
        raise NotFound("Connect this provider first.")
    ids = await lister(provider, _decrypt(row), _base_url(provider, row))
    return [ModelOut(id=i, free=is_free_model(provider_id, i)) for i in ids]


# ------------------------------------------------------------------ write


async def connect(
    session: AsyncSession,
    user_id: uuid.UUID,
    provider_id: str,
    data: ConnectionIn,
    *,
    settings: Settings,
    lister: ModelLister,
    request: Request | None = None,
) -> ConnectionsOut:
    """Check the key/endpoint with the provider, then store it (encrypted)."""
    provider = get_provider(provider_id)
    row = await _row(session, user_id, provider_id)

    key = data.api_key.get_secret_value().strip() if data.api_key else None
    if key:
        _check_key_format(provider, key)
    elif row is not None:
        key = _decrypt(row)  # keep the stored key when only the model or URL changes
    if provider.needs_key and not key:
        raise BadRequest(f"{provider.name} needs an API key.", code="ai_key_required_field")

    base_url: str | None = None
    if provider.custom_url:
        raw = data.base_url or (row.base_url if row else None) or provider.base_url
        if not raw:
            raise BadRequest("Enter the endpoint URL.", code="ai_url_invalid")
        base_url = await check_base_url(raw, allow_private=settings.private_endpoints_allowed)

    models = await lister(provider, key, base_url or provider.base_url)  # verifies the key

    if row is None:
        row = AICredential(user_id=user_id, provider=provider_id)
        session.add(row)
    row.key_enc = (
        get_keyring().encrypt(key.encode(), aad=_aad(user_id, provider_id)) if key else None
    )
    row.key_hint = _hint(key) if key else None
    row.base_url = base_url
    model = (data.model or "").strip() or row.model or provider.default_model
    if model is None and len(models) == 1:
        model = models[0]
    row.model = model
    row.verified_at = utc_now()
    await session.flush()
    has_active = await session.scalar(
        select(AICredential.id).where(AICredential.user_id == user_id, AICredential.is_active)
    )
    if row.model and (data.activate or not has_active):
        await _activate(session, user_id, row)
    identity_service.audit_event(
        session,
        user_id=user_id,
        action="ai_connection.set",
        entity_type="ai_credential",
        details={"provider": provider_id, "hint": row.key_hint, "model": row.model},
        request=request,
    )
    await session.commit()
    return await overview(session, user_id, settings)


async def change(
    session: AsyncSession,
    user_id: uuid.UUID,
    provider_id: str,
    data: ConnectionUpdate,
    *,
    settings: Settings,
    request: Request | None = None,
) -> ConnectionsOut:
    """Pick a different model, or make this connection the active one. No re-check needed."""
    get_provider(provider_id)
    row = await _row(session, user_id, provider_id)
    if row is None:
        raise NotFound("Connect this provider first.")
    if data.model is not None:
        model = data.model.strip()
        if not model:
            raise BadRequest("Pick a model.", code="ai_model_required")
        row.model = model
    if data.active:
        await _activate(session, user_id, row)
    elif data.active is False:
        row.is_active = False
    identity_service.audit_event(
        session,
        user_id=user_id,
        action="ai_connection.change",
        entity_type="ai_credential",
        details={"provider": provider_id, "model": row.model, "active": row.is_active},
        request=request,
    )
    await session.commit()
    return await overview(session, user_id, settings)


async def disconnect(
    session: AsyncSession,
    user_id: uuid.UUID,
    provider_id: str,
    *,
    settings: Settings,
    request: Request | None = None,
) -> ConnectionsOut:
    row = await _row(session, user_id, provider_id)
    if row is not None:
        await session.delete(row)
        identity_service.audit_event(
            session,
            user_id=user_id,
            action="ai_connection.delete",
            entity_type="ai_credential",
            details={"provider": provider_id, "hint": row.key_hint},
            request=request,
        )
        await session.commit()
    return await overview(session, user_id, settings)
