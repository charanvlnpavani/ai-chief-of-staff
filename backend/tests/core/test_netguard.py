"""Outbound-request guard: private addresses are refused at connect time, not only at save time."""

import asyncio
import socket
from collections.abc import Callable
from typing import Any

import httpx
import httpx2
import openai
import pytest

from app.ai import connections
from app.ai.openai_compat import OpenAICompatibleChatModel
from app.ai.providers import PROVIDERS, check_base_url, openai_http_client
from app.core import netguard
from app.core.errors import BadRequest, ServiceUnavailable
from app.modules.roadmaps.generator import OpenAICompatibleRoadmapGenerator

PUBLIC_V4 = "93.184.216.34"
PUBLIC_V6 = "2606:4700::1111"


def fake_dns(monkeypatch: pytest.MonkeyPatch, answers: dict[str, list[str]]) -> list[str]:
    """Answer getaddrinfo from `answers`; returns the list of looked-up hosts."""
    lookups: list[str] = []

    async def getaddrinfo(
        self: asyncio.AbstractEventLoop, host: str, port: int, **_: Any
    ) -> list[tuple[Any, ...]]:
        lookups.append(host)
        if host not in answers:
            raise socket.gaierror(socket.EAI_NONAME, "not found")
        return [
            (
                socket.AF_INET6 if ":" in a else socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                (a, port),
            )
            for a in answers[host]
        ]

    monkeypatch.setattr(asyncio.BaseEventLoop, "getaddrinfo", getaddrinfo)
    return lookups


def recording_transport(
    handler: Callable[[httpx.Request], httpx.Response] | None = None,
) -> tuple[netguard.PublicOnlyTransport, list[httpx.Request]]:
    sent: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return handler(request) if handler else httpx.Response(200, text="ok")

    return netguard.PublicOnlyTransport(httpx.MockTransport(handle)), sent


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.5",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",  # cloud metadata
        "100.64.0.1",  # carrier-grade NAT / Tailscale
        "100.100.100.200",  # metadata in shared address space
        "0.0.0.0",  # noqa: S104 (an address to block, not a bind)
        "224.0.0.1",
        "::1",
        "fc00::1",
        "fe80::1",
        "::ffff:127.0.0.1",  # IPv4-mapped loopback
        "::ffff:10.0.0.1",
    ],
)
def test_non_public_addresses_are_blocked(address: str) -> None:
    assert netguard.is_blocked_ip(address)


@pytest.mark.parametrize("address", [PUBLIC_V4, "8.8.8.8", PUBLIC_V6])
def test_public_addresses_are_allowed(address: str) -> None:
    assert not netguard.is_blocked_ip(address)


async def test_every_dns_answer_is_checked(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_dns(
        monkeypatch,
        {"ok.test": [PUBLIC_V4, PUBLIC_V6], "mixed.test": [PUBLIC_V4, "10.0.0.1"]},
    )
    assert await netguard.resolve_public("ok.test", 443) == [PUBLIC_V4, PUBLIC_V6]
    with pytest.raises(netguard.BlockedAddress):
        await netguard.resolve_public("mixed.test", 443)
    with pytest.raises(netguard.UnresolvableHost):
        await netguard.resolve_public("missing.test", 443)
    with pytest.raises(netguard.BlockedAddress):
        await netguard.resolve_public("[::1]", 443)


async def test_transport_connects_to_the_checked_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_dns(monkeypatch, {"api.example.test": [PUBLIC_V4]})
    transport, sent = recording_transport()
    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get("https://api.example.test/v1/models?x=1")

    assert response.status_code == 200
    (pinned,) = sent
    assert pinned.url == httpx.URL(f"https://{PUBLIC_V4}/v1/models?x=1")
    assert pinned.headers["host"] == "api.example.test"
    assert pinned.extensions["sni_hostname"] == "api.example.test"
    # The client's own view keeps the host name.
    assert response.request.url.host == "api.example.test"


async def test_plain_http_is_pinned_without_sni(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_dns(monkeypatch, {"plain.test": [PUBLIC_V6]})
    transport, sent = recording_transport()
    async with httpx.AsyncClient(transport=transport) as client:
        await client.get("http://plain.test:8080/a")
    assert str(sent[0].url) == f"http://[{PUBLIC_V6}]:8080/a"
    assert "sni_hostname" not in sent[0].extensions


async def test_rebinding_to_a_private_address_is_refused_at_connect_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The host passed the save-time check, then its DNS answer changed."""
    answers = {"rebind.test": [PUBLIC_V4]}
    fake_dns(monkeypatch, answers)
    assert await check_base_url("https://rebind.test/v1", allow_private=False)

    answers["rebind.test"] = ["127.0.0.1"]
    transport, sent = recording_transport()
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(netguard.BlockedAddress):
            await client.get("https://rebind.test/v1/models")
    assert sent == []


async def test_each_redirect_hop_is_checked(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_dns(monkeypatch, {"start.test": [PUBLIC_V4], "internal.test": ["10.0.0.7"]})

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/next"})
        if request.url.path == "/next":
            return httpx.Response(302, headers={"location": "http://internal.test/admin"})
        return httpx.Response(200)

    transport, sent = recording_transport(handler)
    async with httpx.AsyncClient(transport=transport, follow_redirects=True) as client:
        with pytest.raises(netguard.BlockedAddress):
            await client.get("https://start.test/start")
    # The relative redirect kept the original host name (Host header and SNI intact).
    assert [r.url.path for r in sent] == ["/start", "/next"]
    assert sent[1].headers["host"] == "start.test"
    assert sent[1].extensions["sni_hostname"] == "start.test"


def test_openai_clients_are_guarded_unless_private_endpoints_are_allowed() -> None:
    assert openai_http_client(allow_private=True) is None
    guarded = openai_http_client(allow_private=False)
    assert isinstance(guarded, httpx2.AsyncClient)
    assert isinstance(guarded._transport, netguard.PublicOnlyTransportHttpx2)

    chat = OpenAICompatibleChatModel(
        provider="custom",
        api_key="k",
        base_url="https://x.test/v1",
        model="m",
        max_tokens=10,
        free=False,
    )
    assert isinstance(chat._client._client._transport, netguard.PublicOnlyTransportHttpx2)
    roadmap = OpenAICompatibleRoadmapGenerator(
        api_key="k", base_url="https://x.test/v1", model="m", free=False
    )
    assert isinstance(roadmap._client._client._transport, netguard.PublicOnlyTransportHttpx2)
    local = OpenAICompatibleChatModel(
        provider="ollama",
        api_key=None,
        base_url="http://localhost:11434/v1",
        model="m",
        max_tokens=10,
        free=True,
        allow_private=True,
    )
    assert not isinstance(local._client._client._transport, netguard.PublicOnlyTransportHttpx2)


async def test_openai_sdk_requests_go_through_the_pinned_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End to end through the SDK (which runs on httpx2), not just a type check."""
    fake_dns(monkeypatch, {"llm.example.test": [PUBLIC_V4]})
    sent: list[httpx2.Request] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        sent.append(request)
        return httpx2.Response(
            200,
            json={
                "object": "list",
                "data": [{"id": "model-a", "object": "model", "created": 0, "owned_by": "x"}],
            },
        )

    client = openai.AsyncOpenAI(
        api_key="k",
        base_url="https://llm.example.test/v1",
        max_retries=0,
        http_client=openai.DefaultAsyncHttpxClient(
            transport=netguard.PublicOnlyTransportHttpx2(httpx2.MockTransport(handle))
        ),
    )
    ids = [m.id async for m in client.models.list()]
    await client.close()

    assert ids == ["model-a"]
    (pinned,) = sent
    assert pinned.url.host == PUBLIC_V4
    assert pinned.headers["host"] == "llm.example.test"
    assert pinned.extensions["sni_hostname"] == "llm.example.test"


async def test_model_listing_reports_a_rebound_endpoint_as_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_dns(monkeypatch, {"rebind.test": ["169.254.169.254"]})
    monkeypatch.setattr(
        connections, "get_settings", lambda: type("S", (), {"private_endpoints_allowed": False})
    )
    with pytest.raises(ServiceUnavailable) as error:
        await connections.list_models_live(PROVIDERS["custom"], "k", "https://rebind.test/v1")
    assert error.value.code == "ai_endpoint_unreachable"
    assert isinstance(error.value.__cause__, openai.APIConnectionError)


async def test_save_time_check_still_names_the_problem(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_dns(monkeypatch, {"internal.test": ["10.1.2.3"]})
    with pytest.raises(BadRequest) as private:
        await check_base_url("https://internal.test/v1", allow_private=False)
    assert private.value.code == "ai_url_private"
    with pytest.raises(BadRequest) as missing:
        await check_base_url("https://missing.test/v1", allow_private=False)
    assert missing.value.code == "ai_url_invalid"
