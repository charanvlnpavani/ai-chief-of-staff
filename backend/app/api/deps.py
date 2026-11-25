"""Shared FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.errors import Unauthorized
from app.modules.identity.service import AuthContext, resolve_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def _extract_token(request: Request, settings: Settings) -> str | None:
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        return token or None
    return request.cookies.get(settings.session_cookie_name) or None


async def get_auth(request: Request, session: SessionDep, settings: SettingsDep) -> AuthContext:
    token = _extract_token(request, settings)
    if token is None:
        raise Unauthorized()
    context = await resolve_session(session, token, settings)
    if context is None:
        raise Unauthorized(
            "Your session has expired. Please sign in again.", code="session_expired"
        )
    return context


CurrentAuth = Annotated[AuthContext, Depends(get_auth)]
