"""Chief of Staff endpoints. Replies stream as Server-Sent Events."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import StreamingResponse

from app.ai import catalog as _catalog  # noqa: F401  (registers tools)
from app.ai import connections, service
from app.ai.client import ChatModel, get_chat_model
from app.ai.orchestrator import SessionFactory, TurnRequest, run_turn
from app.ai.registry import Level, registry
from app.ai.schemas import (
    AIStatusOut,
    ConnectionIn,
    ConnectionsOut,
    ConnectionUpdate,
    ConversationDetailOut,
    ConversationIn,
    ConversationOut,
    MessageIn,
    ModelOut,
    ProviderOut,
    ToolInfoOut,
    UsageOut,
)
from app.api.deps import CurrentAuth, SessionDep, SettingsDep
from app.core.db import get_session_factory
from app.core.errors import Forbidden
from app.core.ratelimit import limiter
from app.core.time import local_today, utc_now
from app.modules.identity import service as identity_service

router = APIRouter(prefix="/ai", tags=["ai"])

ChatModelDep = Annotated[ChatModel, Depends(get_chat_model)]
ListerDep = Annotated[connections.ModelLister, Depends(connections.get_model_lister)]
SessionFactoryDep = Annotated[SessionFactory, Depends(get_session_factory)]
CEILING = Level.SUGGEST  # Release 1: read and suggest only


async def _budget_usd(auth: CurrentAuth, session: SessionDep) -> float:
    preferences, _version = await identity_service.get_preferences(session, auth.user.id)
    return preferences.ai.monthly_budget_usd


@router.get("/status", response_model=AIStatusOut)
async def ai_status(auth: CurrentAuth, session: SessionDep, settings: SettingsDep) -> AIStatusOut:
    today = local_today(auth.user.timezone)
    spent = await service.month_to_date_micros(
        session, auth.user.id, timezone=auth.user.timezone, today=today
    )
    budget = await _budget_usd(auth, session)
    active = await connections.resolve_connection(session, auth.user.id, settings)
    return AIStatusOut(
        enabled=active is not None,
        key_source=active.source if active else None,
        provider=active.provider if active else None,
        model=active.model if active else settings.ai_model_chat,
        consent_granted=await identity_service.has_consent(session, auth.user.id, "ai_processing"),
        month_to_date_usd=round(spent / 1_000_000, 4),
        monthly_budget_usd=budget,
        budget_remaining_usd=round(max(budget - spent / 1_000_000, 0), 4),
    )


@router.get("/providers", response_model=list[ProviderOut])
async def list_providers(auth: CurrentAuth) -> list[ProviderOut]:
    """AI providers you can connect with your own key (or local Ollama, no key)."""
    return connections.list_providers()


@router.get("/connections", response_model=ConnectionsOut)
async def get_connections(
    auth: CurrentAuth, session: SessionDep, settings: SettingsDep
) -> ConnectionsOut:
    """Your connected providers and which one is active. Keys are never returned."""
    return await connections.overview(session, auth.user.id, settings)


@router.put("/connections/{provider}", response_model=ConnectionsOut)
async def connect_provider(
    provider: str,
    payload: ConnectionIn,
    request: Request,
    auth: CurrentAuth,
    session: SessionDep,
    settings: SettingsDep,
    lister: ListerDep,
) -> ConnectionsOut:
    """Check the key (and endpoint) with the provider, then store it encrypted."""
    limiter.hit(f"ai-connect:{auth.user.id}", limit=10, window_seconds=300)
    return await connections.connect(
        session, auth.user.id, provider, payload, settings=settings, lister=lister, request=request
    )


@router.patch("/connections/{provider}", response_model=ConnectionsOut)
async def change_connection(
    provider: str,
    payload: ConnectionUpdate,
    request: Request,
    auth: CurrentAuth,
    session: SessionDep,
    settings: SettingsDep,
) -> ConnectionsOut:
    """Pick another model, or make this provider the active one."""
    return await connections.change(
        session, auth.user.id, provider, payload, settings=settings, request=request
    )


@router.delete("/connections/{provider}", response_model=ConnectionsOut)
async def disconnect_provider(
    provider: str, request: Request, auth: CurrentAuth, session: SessionDep, settings: SettingsDep
) -> ConnectionsOut:
    return await connections.disconnect(
        session, auth.user.id, provider, settings=settings, request=request
    )


@router.get("/connections/{provider}/models", response_model=list[ModelOut])
async def provider_models(
    provider: str, auth: CurrentAuth, session: SessionDep, lister: ListerDep
) -> list[ModelOut]:
    """The provider's live model list, fetched with your key (installed models for Ollama)."""
    limiter.hit(f"ai-models:{auth.user.id}", limit=20, window_seconds=60)
    return await connections.available_models(session, auth.user.id, provider, lister=lister)


@router.get("/tools", response_model=list[ToolInfoOut])
async def list_tools(auth: CurrentAuth, session: SessionDep) -> list[ToolInfoOut]:
    consented = await identity_service.has_consent(session, auth.user.id, "ai_processing")
    granted = {"ai_processing"} if consented else set()
    available = {t.name for t in registry.allowed(ceiling=CEILING, granted_consents=granted)}
    return [
        ToolInfoOut(
            name=t.name,
            description=t.description,
            level=int(t.level),
            consent=t.consent,
            available=t.name in available,
        )
        for t in registry.all()
    ]


@router.get("/usage", response_model=UsageOut)
async def usage(auth: CurrentAuth, session: SessionDep) -> UsageOut:
    today = local_today(auth.user.timezone)
    spent = await service.month_to_date_micros(
        session, auth.user.id, timezone=auth.user.timezone, today=today
    )
    return UsageOut(
        month=today.strftime("%Y-%m"),
        month_to_date_usd=round(spent / 1_000_000, 4),
        monthly_budget_usd=await _budget_usd(auth, session),
        by_route=await service.usage_by_route(
            session, auth.user.id, timezone=auth.user.timezone, today=today
        ),
    )


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(auth: CurrentAuth, session: SessionDep) -> list[ConversationOut]:
    rows = await service.list_conversations(session, auth.user.id)
    return [ConversationOut.model_validate(r) for r in rows]


@router.post("/conversations", response_model=ConversationOut, status_code=201)
async def create_conversation(
    payload: ConversationIn, auth: CurrentAuth, session: SessionDep, settings: SettingsDep
) -> ConversationOut:
    conversation = await service.create_conversation(
        session, auth.user.id, title=payload.title, settings=settings
    )
    return ConversationOut.model_validate(conversation)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailOut)
async def get_conversation(
    conversation_id: uuid.UUID, auth: CurrentAuth, session: SessionDep
) -> ConversationDetailOut:
    return await service.conversation_detail(session, auth.user.id, conversation_id)


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: uuid.UUID, auth: CurrentAuth, session: SessionDep
) -> Response:
    await service.delete_conversation(session, auth.user.id, conversation_id)
    return Response(status_code=204)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def send_message(
    conversation_id: uuid.UUID,
    payload: MessageIn,
    auth: CurrentAuth,
    session: SessionDep,
    settings: SettingsDep,
    model: ChatModelDep,
    session_factory: SessionFactoryDep,
) -> StreamingResponse:
    limiter.hit(f"ai:{auth.user.id}", limit=20, window_seconds=60)
    await service.get_conversation(session, auth.user.id, conversation_id)  # ownership
    if not await identity_service.has_consent(session, auth.user.id, "ai_processing"):
        raise Forbidden(
            "Allow the Chief of Staff to process your Personal OS data first.",
            code="consent_required",
            category="ai_processing",
        )
    today = local_today(auth.user.timezone)
    budget_micros = int((await _budget_usd(auth, session)) * 1_000_000)
    spent = await service.month_to_date_micros(
        session, auth.user.id, timezone=auth.user.timezone, today=today
    )
    if spent >= budget_micros:
        raise Forbidden(
            "You have reached this month's AI budget. Raise it in Settings to continue.",
            code="ai_budget_exceeded",
        )
    request = TurnRequest(
        conversation_id=conversation_id,
        user_id=auth.user.id,
        timezone=auth.user.timezone,
        today=today,
        now=utc_now(),
        text=payload.content,
        budget_micros=budget_micros,
        tools=registry.allowed(ceiling=CEILING, granted_consents={"ai_processing"}),
        max_iterations=settings.ai_max_tool_iterations,
    )
    return StreamingResponse(
        run_turn(session_factory=session_factory, model=model, request=request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
