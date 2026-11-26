"""AI provider connections: any provider, model choice, encryption, isolation, URL safety,
and real OpenAI-SDK round trips against a fake HTTP server (no network, no cost)."""

import json
import re
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest
from cryptography.exceptions import InvalidTag
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import connections
from app.ai.client import get_chat_model, model_for_connection
from app.ai.models import AICredential, AIUsageLedger
from app.ai.openai_compat import OpenAICompatibleChatModel
from app.ai.pricing import Usage, cost_micros
from app.ai.providers import Provider, check_base_url
from app.core.config import Settings
from app.core.errors import BadRequest
from app.modules.identity.models import AuditLog
from app.modules.roadmaps import router as roadmaps_router
from app.modules.roadmaps.generator import OpenAICompatibleRoadmapGenerator

CLAUDE_KEY = "sk-ant-api03-" + "a1B2c3D4e5" * 4 + "wxyz"
OPENAI_KEY = "sk-proj-" + "q" * 40 + "abcd"
BASE = "/api/v1/ai"


class FakeLister:
    def __init__(self) -> None:
        self.reject = False
        self.calls: list[tuple[str, str | None, str | None]] = []
        self.models: dict[str, list[str]] = {
            "anthropic": ["claude-opus-5-5", "claude-sonnet-5-5"],
            "openai": ["model-a", "model-b"],
            "openrouter": ["vendor/big-model", "vendor/small-model:free"],
            "ollama": ["llama-local"],
        }

    async def __call__(self, provider: Provider, key: str | None, url: str | None) -> list[str]:
        self.calls.append((provider.id, key, url))
        if self.reject:
            raise BadRequest(f"{provider.name} rejected this API key.", code="ai_key_invalid")
        return self.models.get(provider.id, [])


@pytest.fixture
def lister(app: FastAPI) -> Iterator[FakeLister]:
    fake = FakeLister()
    app.dependency_overrides[connections.get_model_lister] = lambda: fake
    yield fake
    app.dependency_overrides.pop(connections.get_model_lister, None)


async def user_id(client: AsyncClient) -> uuid.UUID:
    return uuid.UUID((await client.get("/api/v1/users/me")).json()["user"]["id"])


def settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "environment": "test",
        "anthropic_api_key": "",
        "ai_key_mode": "user",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


# ------------------------------------------------------------------ catalogue and connecting


async def test_provider_catalogue(owner: AsyncClient) -> None:
    providers = {p["id"]: p for p in (await owner.get(f"{BASE}/providers")).json()}
    assert set(providers) == {
        "anthropic",
        "openai",
        "gemini",
        "openrouter",
        "groq",
        "ollama",
        "custom",
    }
    assert providers["ollama"]["needsKey"] is False
    assert providers["anthropic"]["kind"] == "anthropic"
    assert providers["gemini"]["kind"] == "openai_compatible"
    status = (await owner.get(f"{BASE}/connections")).json()
    assert status == {"mode": "user", "active": None, "connections": []}


async def test_connect_claude_then_switch_to_openai(
    owner: AsyncClient, lister: FakeLister, db_session: AsyncSession
) -> None:
    claude = (await owner.put(f"{BASE}/connections/anthropic", json={"apiKey": CLAUDE_KEY})).json()
    assert claude["active"] == {
        "provider": "anthropic",
        "providerName": "Claude (Anthropic)",
        "model": "claude-opus-5-5",  # Claude's default model
        "source": "user",
        "free": False,
    }
    assert CLAUDE_KEY not in json.dumps(claude)
    assert claude["connections"][0]["hint"] == "…wxyz"

    # Connect OpenAI without switching to it yet; no model chosen.
    openai_conn = (
        await owner.put(
            f"{BASE}/connections/openai", json={"apiKey": OPENAI_KEY, "activate": False}
        )
    ).json()
    assert openai_conn["active"]["provider"] == "anthropic"
    models = (await owner.get(f"{BASE}/connections/openai/models")).json()
    assert models == [{"id": "model-a", "free": False}, {"id": "model-b", "free": False}]
    no_model = await owner.patch(f"{BASE}/connections/openai", json={"active": True})
    assert no_model.json()["code"] == "ai_model_required"
    switched = (
        await owner.patch(f"{BASE}/connections/openai", json={"model": "model-b", "active": True})
    ).json()
    assert switched["active"]["provider"] == "openai"
    assert switched["active"]["model"] == "model-b"
    assert [c["active"] for c in switched["connections"]] == [False, True]  # only one active

    me = await user_id(owner)
    rows = list(await db_session.scalars(select(AICredential).where(AICredential.user_id == me)))
    for row in rows:
        assert row.key_enc is not None
        assert CLAUDE_KEY.encode() not in row.key_enc
        assert OPENAI_KEY.encode() not in row.key_enc
    active = await connections.resolve_connection(db_session, me, settings())
    assert active is not None
    assert (active.provider, active.api_key, active.model) == ("openai", OPENAI_KEY, "model-b")
    assert active.base_url == "https://api.openai.com/v1"
    actions = [
        a.action for a in await db_session.scalars(select(AuditLog).where(AuditLog.user_id == me))
    ]
    assert actions.count("ai_connection.set") == 2
    assert actions.count("ai_connection.change") == 1  # the model-less switch was refused


async def test_free_models_are_marked_and_cost_nothing(
    owner: AsyncClient, lister: FakeLister
) -> None:
    await owner.put(
        f"{BASE}/connections/openrouter",
        json={"apiKey": OPENAI_KEY, "model": "vendor/small-model:free"},
    )
    status = (await owner.get(f"{BASE}/connections")).json()
    assert status["active"]["free"] is True
    models = (await owner.get(f"{BASE}/connections/openrouter/models")).json()
    assert {m["id"]: m["free"] for m in models} == {
        "vendor/big-model": False,
        "vendor/small-model:free": True,
    }
    usage = Usage(input_tokens=10_000, output_tokens=10_000)
    assert cost_micros("vendor/small-model:free", usage, free=True) == 0
    assert cost_micros("unknown-model", usage) > 0  # unknown prices still count against the budget


async def test_ollama_needs_no_key_and_picks_the_only_model(
    owner: AsyncClient, lister: FakeLister
) -> None:
    connected = (
        await owner.put(
            f"{BASE}/connections/ollama", json={"baseUrl": "http://localhost:11434/v1/"}
        )
    ).json()
    assert connected["active"]["provider"] == "ollama"
    assert connected["active"]["model"] == "llama-local"
    assert connected["active"]["free"] is True
    assert connected["connections"][0]["hint"] is None
    assert connected["connections"][0]["baseUrl"] == "http://localhost:11434/v1"
    assert lister.calls[-1] == ("ollama", None, "http://localhost:11434/v1")


async def test_bad_keys_are_not_stored(owner: AsyncClient, lister: FakeLister) -> None:
    wrong_shape = await owner.put(
        f"{BASE}/connections/anthropic", json={"apiKey": "sk-proj-" + "1" * 9}
    )
    assert wrong_shape.json()["code"] == "ai_key_format"
    missing = await owner.put(f"{BASE}/connections/openai", json={})
    assert missing.json()["code"] == "ai_key_required_field"
    assert lister.calls == []  # nothing sent to a provider
    lister.reject = True
    rejected = await owner.put(f"{BASE}/connections/openai", json={"apiKey": OPENAI_KEY})
    assert rejected.json()["code"] == "ai_key_invalid"
    assert (await owner.get(f"{BASE}/connections")).json()["connections"] == []
    unknown = await owner.put(f"{BASE}/connections/skynet", json={"apiKey": OPENAI_KEY})
    assert unknown.json()["code"] == "unknown_provider"


async def test_disconnect_and_per_user_isolation(
    owner: AsyncClient, intruder: AsyncClient, lister: FakeLister, db_session: AsyncSession
) -> None:
    await owner.put(f"{BASE}/connections/openai", json={"apiKey": OPENAI_KEY, "model": "model-a"})
    assert (await intruder.get(f"{BASE}/connections")).json()["connections"] == []
    assert (await intruder.get(f"{BASE}/connections/openai/models")).status_code == 404
    other = await user_id(intruder)
    assert await connections.resolve_connection(db_session, other, settings()) is None
    # A key copied into another user's row does not decrypt (AAD binds it to its owner).
    owner_row = await db_session.scalar(
        select(AICredential).where(AICredential.user_id == await user_id(owner))
    )
    assert owner_row is not None
    db_session.add(
        AICredential(
            user_id=other, provider="openai", key_enc=owner_row.key_enc, model="m", is_active=True
        )
    )
    await db_session.flush()
    with pytest.raises(InvalidTag):
        await connections.resolve_connection(db_session, other, settings())
    await db_session.rollback()
    gone = (await owner.delete(f"{BASE}/connections/openai")).json()
    assert gone == {"mode": "user", "active": None, "connections": []}


async def test_server_mode_fallback_and_production_guard(
    owner: AsyncClient, lister: FakeLister, db_session: AsyncSession
) -> None:
    me = await user_id(owner)
    shared = "sk-ant-api03-" + "s" * 40
    assert (
        await connections.resolve_connection(db_session, me, settings(anthropic_api_key=shared))
        is None
    )
    server = settings(anthropic_api_key=shared, ai_key_mode="server")
    fallback = await connections.resolve_connection(db_session, me, server)
    assert fallback is not None
    assert (fallback.source, fallback.api_key) == ("server", shared)
    await owner.put(f"{BASE}/connections/openai", json={"apiKey": OPENAI_KEY, "model": "model-a"})
    mine = await connections.resolve_connection(db_session, me, server)
    assert mine is not None
    assert (mine.source, mine.provider) == ("user", "openai")  # a personal connection wins
    with pytest.raises(ValidationError, match="AI_KEY_MODE must be 'user'"):
        Settings(
            environment="production",
            secret_key="x" * 40,  # type: ignore[arg-type]
            encryption_keys="k:" + "A" * 43 + "=",  # type: ignore[arg-type]
            dev_login_enabled=False,
            ai_key_mode="server",
        )
    production = Settings(
        environment="production",
        secret_key="x" * 40,  # type: ignore[arg-type]
        encryption_keys="k:" + "A" * 43 + "=",  # type: ignore[arg-type]
        dev_login_enabled=False,
    )
    assert production.private_endpoints_allowed is False


async def test_provider_urls_cannot_reach_private_networks_in_production() -> None:
    for url in (
        "http://localhost:11434/v1",
        "https://127.0.0.1/v1",
        "https://10.0.0.5/v1",
        "https://169.254.169.254/latest",
        "https://[::1]/v1",
    ):
        with pytest.raises(BadRequest) as error:
            await check_base_url(url, allow_private=False)
        assert error.value.code in ("ai_url_private", "ai_url_invalid")
    with pytest.raises(BadRequest):
        await check_base_url("https://user:pass@example.com/v1", allow_private=True)
    with pytest.raises(BadRequest):
        await check_base_url("ftp://example.com", allow_private=True)
    assert (
        await check_base_url("http://localhost:11434/v1/", allow_private=True)
        == "http://localhost:11434/v1"
    )


def test_each_connection_gets_its_own_client() -> None:
    a = connections.Connection(
        "openai", "openai_compatible", OPENAI_KEY, "https://api.openai.com/v1", "model-a", "user"
    )
    b = connections.Connection(
        "openai", "openai_compatible", OPENAI_KEY, "https://api.openai.com/v1", "model-b", "user"
    )
    assert model_for_connection(a) is model_for_connection(a)
    assert model_for_connection(a) is not model_for_connection(b)
    assert isinstance(model_for_connection(a), OpenAICompatibleChatModel)


# ------------------------------------------------------------------ real SDK, fake server


def sse(*events: dict[str, Any]) -> httpx.Response:
    body = "".join(f"data: {json.dumps(e)}\n\n" for e in events) + "data: [DONE]\n\n"
    return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})


def chunk(delta: dict[str, Any], finish: str | None = None) -> dict[str, Any]:
    return {
        "id": "c",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "model-a",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }


def usage_chunk() -> dict[str, Any]:
    return {
        "id": "c",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "model-a",
        "choices": [],
        "usage": {"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60},
    }


def fake_openai(handler: Callable[[httpx.Request], httpx.Response], model: Any) -> None:
    import openai

    model._client = openai.AsyncOpenAI(
        api_key="test",
        base_url="https://fake.test/v1",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


async def test_chief_of_staff_tool_loop_runs_on_an_openai_compatible_model(
    app: FastAPI, owner: AsyncClient, db_session: AsyncSession
) -> None:
    requests: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:  # first turn: the model asks for a tool
            return sse(
                chunk({"role": "assistant", "content": "Looking."}),
                chunk(
                    {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_1",
                                "type": "function",
                                "function": {"name": "list_tasks", "arguments": ""},
                            }
                        ]
                    }
                ),
                chunk({"tool_calls": [{"index": 0, "function": {"arguments": "{}"}}]}),
                chunk({}, "tool_calls"),
                usage_chunk(),
            )
        return sse(chunk({"content": "You have no tasks."}), chunk({}, "stop"), usage_chunk())

    model = OpenAICompatibleChatModel(
        provider="openai",
        api_key="k",
        base_url="https://fake.test/v1",
        model="model-a",
        max_tokens=1000,
        free=False,
    )
    fake_openai(handler, model)
    app.dependency_overrides[get_chat_model] = lambda: model
    await owner.put("/api/v1/users/me/consents/ai_processing", json={"granted": True})
    conversation = (await owner.post(f"{BASE}/conversations", json={})).json()["id"]
    reply = await owner.post(
        f"{BASE}/conversations/{conversation}/messages", json={"content": "What is due?"}
    )
    assert reply.status_code == 200
    assert "You have no tasks." in reply.text
    assert len(requests) == 2
    assert any(t["function"]["name"] == "list_tasks" for t in requests[0]["tools"])
    second = requests[1]["messages"]
    assert second[-2]["tool_calls"][0]["id"] == "call_1"
    assert second[-1]["role"] == "tool"
    assert second[-1]["tool_call_id"] == "call_1"
    ledger = list(
        await db_session.scalars(select(AIUsageLedger).where(AIUsageLedger.route == "chat"))
    )
    assert len(ledger) == 2
    assert ledger[0].model == "model-a"
    app.dependency_overrides.pop(get_chat_model, None)


async def test_roadmap_draft_from_a_local_model(
    app: FastAPI, owner: AsyncClient, db_session: AsyncSession
) -> None:
    def reply_for(body: dict[str, Any]) -> dict[str, Any]:
        system, user = body["messages"][0]["content"], body["messages"][1]["content"]
        if system.startswith("You design"):  # stage 1: outline, two concepts per level
            return {
                "title": "Rust: zero to pro",
                "levels": [
                    {"level": lv, "topics": [f"{lv} idea 1", f"{lv} idea 2"]}
                    for lv in ("basic", "intermediate", "advanced", "pro")
                ],
            }
        topics = re.findall(r"^Day \d+: (.+)$", user, flags=re.MULTILINE)  # stage 2
        return {
            "days": [
                {
                    "topic": t,
                    "tasks": [{"title": f"Understand: {t}", "detail": "Why.", "minutes": 60}],
                }
                for t in topics
            ]
        }

    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        if "response_format" in body:  # this "local model" has no structured output
            return httpx.Response(400, json={"error": {"message": "response_format not supported"}})
        return httpx.Response(
            200,
            json={
                "id": "x",
                "object": "chat.completion",
                "created": 0,
                "model": "llama-local",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": "Here:\n```json\n" + json.dumps(reply_for(body)) + "\n```",
                        },
                    }
                ],
                "usage": {"prompt_tokens": 900, "completion_tokens": 400, "total_tokens": 1300},
            },
        )

    generator = OpenAICompatibleRoadmapGenerator(
        api_key=None, base_url="http://localhost:11434/v1", model="llama-local", free=True
    )
    fake_openai(handler, generator)
    app.dependency_overrides[roadmaps_router._optional_generator] = lambda: generator
    await owner.put("/api/v1/users/me/consents/ai_processing", json={"granted": True})
    request = {"subject": "Rust", "targetDays": 8, "minutesPerDay": 60}
    draft = (await owner.post("/api/v1/roadmaps/draft", json=request)).json()
    assert draft["source"] == "ai"
    assert draft["title"] == "Rust: zero to pro"
    assert [d["level"] for d in draft["days"]] == [
        lv for lv in ("basic", "intermediate", "advanced", "pro") for _ in (1, 2)
    ]
    assert draft["days"][0]["tasks"][0]["title"] == "Understand: basic idea 1"
    # Structured output is refused once; the generator remembers and sends plain JSON from
    # then on: outline (2 requests) + one expand call per level (4).
    assert len(seen) == 6
    assert ["response_format" in body for body in seen] == [True] + [False] * 5
    ledger = list(
        await db_session.scalars(select(AIUsageLedger).where(AIUsageLedger.route == "roadmap"))
    )
    assert len(ledger) == 5  # one row per answered call
    assert all(row.cost_usd_micros == 0 for row in ledger)  # local model: free
    app.dependency_overrides.pop(roadmaps_router._optional_generator, None)
