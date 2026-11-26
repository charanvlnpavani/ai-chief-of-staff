"""Outbound requests that must never reach private or local network addresses.

Checking a URL's host once and then letting the HTTP client resolve it again leaves a gap:
a hostile DNS server can answer with a public address for the check and a private one for
the real connection (DNS rebinding). `PublicOnlyTransport` closes it by resolving the host
itself, refusing the request if any answer is non-public, and connecting to the checked
address while still sending the original host name for TLS (SNI and certificate checks)
and in the `Host` header.
"""

import asyncio
import ipaddress
import socket
from typing import Any

import httpx
import httpx2


class BlockedAddress(httpx.TransportError):
    """The host resolves to a private, local or otherwise non-public address."""


class UnresolvableHost(httpx.TransportError):
    """The host name does not resolve."""


# Carrier-grade NAT space: not "private" to `ipaddress`, but used for internal networks
# (Tailscale, some cloud metadata services such as 100.100.100.200).
_SHARED_ADDRESS_SPACE = ipaddress.ip_network("100.64.0.0/10")


def is_blocked_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped  # ::ffff:127.0.0.1 is loopback
    return (
        ip in _SHARED_ADDRESS_SPACE
        or ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


async def resolve_public(host: str, port: int) -> list[str]:
    """Every address `host` resolves to, or an error if any of them is non-public.

    All answers are checked, not just the first, so a round-robin record that mixes a
    public and a private address is refused.
    """
    try:
        literal = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        literal = None
    if literal is not None:
        addresses = [str(literal)]
    else:
        try:
            infos = await asyncio.get_running_loop().getaddrinfo(
                host, port, type=socket.SOCK_STREAM
            )
        except OSError as exc:
            raise UnresolvableHost(f"{host} does not resolve") from exc
        addresses = list(dict.fromkeys(str(info[4][0]) for info in infos))
    if not addresses:
        raise UnresolvableHost(f"{host} does not resolve")
    if any(is_blocked_ip(a) for a in addresses):
        raise BlockedAddress(f"{host} resolves to a non-public address")
    return addresses


class _PinToPublicAddress:
    """Shared logic for the two transports below: resolve, refuse non-public answers, then
    connect to the checked address while sending the original host name for TLS (SNI and
    certificate checks) and in the `Host` header.

    Every request, including each redirect hop the client follows, goes through
    `handle_async_request`, so redirects to private addresses are refused as well.
    Proxies configured through environment variables bypass the transport, and with a proxy
    the proxy resolves the name, so pinning cannot apply.
    """

    _inner: Any

    async def handle_async_request(self, request: Any) -> Any:
        url = request.url
        host = url.host
        port = url.port or (443 if url.scheme == "https" else 80)
        address = (await resolve_public(host, port))[0]
        if address == host.strip("[]"):
            return await self._inner.handle_async_request(request)
        # Send a copy so the client's own request keeps the host name: httpx resolves
        # relative redirects against it. The Host header was set from the original URL.
        extensions = dict(request.extensions)
        if url.scheme == "https":
            extensions["sni_hostname"] = host
        pinned = type(request)(
            request.method,
            url.copy_with(host=address),
            headers=request.headers,
            stream=request.stream,
            extensions=extensions,
        )
        return await self._inner.handle_async_request(pinned)

    async def aclose(self) -> None:
        await self._inner.aclose()


class PublicOnlyTransport(_PinToPublicAddress, httpx.AsyncBaseTransport):
    """For `httpx.AsyncClient` (e.g. fetching saved links' metadata)."""

    def __init__(self, inner: httpx.AsyncBaseTransport | None = None) -> None:
        self._inner = inner or httpx.AsyncHTTPTransport()


class PublicOnlyTransportHttpx2(_PinToPublicAddress, httpx2.AsyncBaseTransport):
    """For OpenAI SDK clients, which run on httpx2: same API as httpx, different types."""

    def __init__(self, inner: httpx2.AsyncBaseTransport | None = None) -> None:
        self._inner = inner or httpx2.AsyncHTTPTransport()
