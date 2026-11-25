"""Application errors rendered as RFC 9457 problem details (`application/problem+json`)."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.errors")

PROBLEM_JSON = "application/problem+json"


class AppError(Exception):
    status_code = 500
    code = "internal_error"
    title = "Internal server error"

    def __init__(
        self,
        detail: str | None = None,
        *,
        code: str | None = None,
        headers: dict[str, str] | None = None,
        **extra: Any,
    ) -> None:
        super().__init__(detail or self.title)
        self.detail = detail
        if code is not None:
            self.code = code
        self.headers = headers or {}
        self.extra = extra


class BadRequest(AppError):
    status_code, code, title = 400, "bad_request", "Bad request"


class Unauthorized(AppError):
    status_code, code, title = 401, "unauthenticated", "Authentication required"


class Forbidden(AppError):
    status_code, code, title = 403, "forbidden", "Forbidden"


class NotFound(AppError):
    status_code, code, title = 404, "not_found", "Not found"


class Conflict(AppError):
    status_code, code, title = 409, "conflict", "Conflict"


class Unprocessable(AppError):
    status_code, code, title = 422, "validation_failed", "Validation failed"


class RateLimited(AppError):
    status_code, code, title = 429, "rate_limited", "Too many requests"


class ServiceUnavailable(AppError):
    status_code, code, title = 503, "service_unavailable", "Service unavailable"


def problem_response(
    request: Request,
    *,
    status: int,
    code: str,
    title: str,
    detail: str | None = None,
    extra: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"urn:personal-os:problem:{code}",
        "title": title,
        "status": status,
        "detail": detail,
        "code": code,
        "instance": request.url.path,
    }
    if extra:
        body.update(extra)
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON, headers=headers)


async def _app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, AppError):  # registered for AppError only; keeps the type checker honest
        raise exc
    return problem_response(
        request,
        status=exc.status_code,
        code=exc.code,
        title=exc.title,
        detail=exc.detail,
        extra=exc.extra,
        headers=exc.headers,
    )


async def _validation_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    # Never echo submitted values back (they may contain personal data).
    errors = [
        {"loc": list(err.get("loc", ())), "msg": err.get("msg", ""), "type": err.get("type", "")}
        for err in exc.errors()
    ]
    return problem_response(
        request,
        status=422,
        code="validation_failed",
        title="Validation failed",
        detail="One or more fields are invalid.",
        extra={"errors": errors},
    )


async def _http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):
        raise exc
    code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
    detail = exc.detail if isinstance(exc.detail, str) else None
    return problem_response(
        request,
        status=exc.status_code,
        code=code,
        title=detail or "HTTP error",
        detail=detail,
        headers=dict(exc.headers or {}),
    )


async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_error", extra={"path": request.url.path})
    return problem_response(
        request,
        status=500,
        code="internal_error",
        title="Internal server error",
        detail="Something went wrong. The error has been logged.",
    )


def install_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(Exception, _unhandled_handler)
