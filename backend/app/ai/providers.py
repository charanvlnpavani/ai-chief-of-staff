"""AI providers a user can connect, and safety checks for provider URLs.

Claude uses Anthropic's own SDK (prompt caching, adaptive thinking, refusal fallback).
Every other provider speaks the OpenAI-compatible Chat Completions API, so one adapter
covers OpenAI, Google Gemini, OpenRouter, Groq, local Ollama and any custom endpoint.
Model names are not hard-coded for those providers: the live model list is fetched with
the user's own key, because providers add and retire models often.
"""

from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

import httpx2
import openai

from app.core import netguard
from app.core.errors import BadRequest

ProviderId = Literal["anthropic", "openai", "gemini", "openrouter", "groq", "ollama", "custom"]
Kind = Literal["anthropic", "openai_compatible"]


@dataclass(frozen=True, slots=True)
class Provider:
    id: ProviderId
    name: str
    kind: Kind
    base_url: str | None
    needs_key: bool
    custom_url: bool
    key_url: str | None
    free_note: str | None
    default_model: str | None = None


PROVIDERS: dict[str, Provider] = {
    p.id: p
    for p in (
        Provider(
            id="anthropic",
            name="Claude (Anthropic)",
            kind="anthropic",
            base_url=None,
            needs_key=True,
            custom_url=False,
            key_url="https://platform.claude.com",
            free_note=None,
            default_model="claude-opus-5-5",
        ),
        Provider(
            id="openai",
            name="ChatGPT models (OpenAI)",
            kind="openai_compatible",
            base_url="https://api.openai.com/v1",
            needs_key=True,
            custom_url=False,
            key_url="https://platform.openai.com/api-keys",
            free_note=None,
        ),
        Provider(
            id="gemini",
            name="Google Gemini",
            kind="openai_compatible",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            needs_key=True,
            custom_url=False,
            key_url="https://aistudio.google.com/apikey",
            free_note="Has a free tier with rate limits.",
        ),
        Provider(
            id="openrouter",
            name="OpenRouter (many models)",
            kind="openai_compatible",
            base_url="https://openrouter.ai/api/v1",
            needs_key=True,
            custom_url=False,
            key_url="https://openrouter.ai/keys",
            free_note="Models whose name ends in :free cost nothing.",
        ),
        Provider(
            id="groq",
            name="Groq",
            kind="openai_compatible",
            base_url="https://api.groq.com/openai/v1",
            needs_key=True,
            custom_url=False,
            key_url="https://console.groq.com/keys",
            free_note="Has a free tier with rate limits.",
        ),
        Provider(
            id="ollama",
            name="Ollama (local, free, offline)",
            kind="openai_compatible",
            base_url="http://localhost:11434/v1",
            needs_key=False,
            custom_url=True,
            key_url="https://ollama.com/download",
            free_note="Runs models on your own computer: free, private and works offline.",
        ),
        Provider(
            id="custom",
            name="Custom OpenAI-compatible endpoint",
            kind="openai_compatible",
            base_url=None,
            needs_key=False,
            custom_url=True,
            key_url=None,
            free_note="LM Studio, DeepSeek, Mistral, Together and others.",
        ),
    )
}


def get_provider(provider_id: str) -> Provider:
    provider = PROVIDERS.get(provider_id)
    if provider is None:
        raise BadRequest("Unknown AI provider.", code="unknown_provider")
    return provider


def is_free_model(provider_id: str, model: str) -> bool:
    return provider_id == "ollama" or model.endswith(":free")


async def check_base_url(url: str, *, allow_private: bool) -> str:
    """Normalise a provider URL and refuse ones that would make the server call internal
    addresses (unless private endpoints are allowed, e.g. a self-host running Ollama)."""
    url = url.strip().rstrip("/")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise BadRequest("Enter a full URL such as https://host/v1.", code="ai_url_invalid")
    if parts.username or parts.password:
        raise BadRequest(
            "Put credentials in the API key field, not the URL.", code="ai_url_invalid"
        )
    if allow_private:
        return url
    if parts.scheme != "https":
        raise BadRequest("Provider URLs must use https.", code="ai_url_invalid")
    try:
        await netguard.resolve_public(parts.hostname, parts.port or 443)
    except netguard.UnresolvableHost as exc:
        raise BadRequest("That host name does not resolve.", code="ai_url_invalid") from exc
    except netguard.BlockedAddress as exc:
        raise BadRequest(
            "Private and local network addresses are not allowed here.", code="ai_url_private"
        ) from exc
    return url


def openai_http_client(*, allow_private: bool) -> httpx2.AsyncClient | None:
    """The HTTP client for OpenAI-compatible endpoints. Without private endpoints allowed,
    every request re-checks the resolved address, so a URL that passed `check_base_url`
    cannot later be pointed at an internal address through DNS. None means the SDK default."""
    if allow_private:
        return None
    return openai.DefaultAsyncHttpxClient(transport=netguard.PublicOnlyTransportHttpx2())
