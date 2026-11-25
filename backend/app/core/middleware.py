"""Request middleware (pure ASGI so streaming responses pass through untouched).

For every HTTP request it:
1. assigns a request id (echoed in `x-request-id`),
2. blocks cross-site state-changing requests that carry the session cookie (CSRF),
3. adds security headers and `Cache-Control: no-store` on API responses,
4. writes one structured access-log line (method, path, status, duration; no query string).
"""

import json
import logging
import re
import uuid
from time import perf_counter

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings
from app.core.logging import request_id_var

logger = logging.getLogger("app.access")

_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_REQUEST_ID = re.compile(r"^[A-Za-z0-9\-]{8,64}$")
_SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "strict-origin-when-cross-origin",
    "x-frame-options": "DENY",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
    "cross-origin-opener-policy": "same-origin",
}


def _cookie_names(cookie_header: str) -> set[str]:
    return {part.split("=", 1)[0].strip() for part in cookie_header.split(";") if "=" in part}


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings
        self.allowed_origins = {settings.web_origin.rstrip("/")}

    def _is_csrf_violation(self, scope: Scope, headers: Headers) -> bool:
        if scope["method"] not in _UNSAFE_METHODS or not scope["path"].startswith("/api/"):
            return False
        if headers.get("authorization", "").lower().startswith("bearer "):
            return False  # bearer tokens are not sent automatically by browsers
        if self.settings.session_cookie_name not in _cookie_names(headers.get("cookie", "")):
            return False  # no ambient credential to abuse
        fetch_site = headers.get("sec-fetch-site")
        if fetch_site is not None:
            return fetch_site not in ("same-origin", "none")
        origin = headers.get("origin")
        if origin is not None:
            return origin.rstrip("/") not in self.allowed_origins
        return True

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        incoming_id = headers.get("x-request-id", "")
        request_id = incoming_id if _REQUEST_ID.match(incoming_id) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        started = perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_headers = MutableHeaders(scope=message)
                response_headers["x-request-id"] = request_id
                for name, value in _SECURITY_HEADERS.items():
                    response_headers.setdefault(name, value)
                if scope["path"].startswith("/api/"):
                    response_headers.setdefault("cache-control", "no-store")
                if self.settings.is_production:
                    response_headers.setdefault(
                        "strict-transport-security", "max-age=31536000; includeSubDomains"
                    )
            await send(message)

        try:
            if self._is_csrf_violation(scope, headers):
                await self._reject_csrf(scope, send_wrapper)
            else:
                await self.app(scope, receive, send_wrapper)
        finally:
            logger.info(
                "request",
                extra={
                    "method": scope["method"],
                    "path": scope["path"],
                    "status": status_code,
                    "duration_ms": round((perf_counter() - started) * 1000, 1),
                },
            )
            request_id_var.reset(token)

    @staticmethod
    async def _reject_csrf(scope: Scope, send: Send) -> None:
        body = json.dumps(
            {
                "type": "urn:personal-os:problem:csrf_rejected",
                "title": "Cross-site request blocked",
                "status": 403,
                "detail": "This request did not come from the Personal OS web app.",
                "code": "csrf_rejected",
                "instance": scope["path"],
            }
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/problem+json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
