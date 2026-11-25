"""Auth and account endpoints."""

import uuid
from typing import Annotated
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import RedirectResponse

from app.api.deps import CurrentAuth, SessionDep, SettingsDep
from app.core.config import Settings
from app.core.errors import Forbidden, NotFound, ServiceUnavailable
from app.core.ratelimit import client_ip, limiter
from app.core.security import new_token, pkce_pair, sign_payload, verify_payload
from app.modules.identity import google, service
from app.modules.identity.schemas import (
    AuthConfigOut,
    ConsentCategory,
    ConsentOut,
    ConsentUpdate,
    DevLoginIn,
    MeOut,
    PreferencesUpdate,
    SessionOut,
    SettingsOut,
    UserOut,
    UserUpdate,
)

auth_router = APIRouter(prefix="/auth", tags=["auth"])
users_router = APIRouter(prefix="/users/me", tags=["users"])

OAUTH_COOKIE = "pos_oauth"
OAUTH_COOKIE_PATH = "/api/v1/auth"


def _rate_limit_auth(request: Request) -> None:
    limiter.hit(f"auth:{client_ip(request)}", limit=20, window_seconds=60)


AuthRateLimit = Annotated[None, Depends(_rate_limit_auth)]


def _safe_next(path: str | None) -> str:
    """Only allow same-site relative paths, to prevent open redirects."""
    if path and path.startswith("/") and not path.startswith("//") and "\\" not in path:
        return path
    return "/today"


def _set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_absolute_days * 86400,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )


def _login_error_redirect(code: str) -> RedirectResponse:
    return RedirectResponse(f"/login?error={quote(code)}", status_code=status.HTTP_303_SEE_OTHER)


# ------------------------------------------------------------------ auth


@auth_router.get("/config", response_model=AuthConfigOut)
async def auth_config(settings: SettingsDep) -> AuthConfigOut:
    return AuthConfigOut(
        google_enabled=settings.google_enabled, dev_login_enabled=settings.dev_login_allowed
    )


@auth_router.get("/google/start", response_class=RedirectResponse, status_code=302)
async def google_start(
    settings: SettingsDep,
    _: AuthRateLimit,
    next_path: Annotated[str | None, Query(alias="next")] = None,
) -> RedirectResponse:
    if not settings.google_enabled:
        raise ServiceUnavailable("Google sign-in is not configured.", code="google_not_configured")
    state, nonce = new_token(24), new_token(24)
    verifier, challenge = pkce_pair()
    cookie_value = sign_payload(
        {"state": state, "nonce": nonce, "verifier": verifier, "next": _safe_next(next_path)},
        settings.secret_key.get_secret_value(),
        ttl_seconds=600,
    )
    response = RedirectResponse(
        google.authorization_url(settings, state=state, nonce=nonce, code_challenge=challenge),
        status_code=302,
    )
    response.set_cookie(
        OAUTH_COOKIE,
        cookie_value,
        max_age=600,
        path=OAUTH_COOKIE_PATH,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return response


@auth_router.get("/google/callback", response_class=RedirectResponse, status_code=303)
async def google_callback(
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    _: AuthRateLimit,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    if error or not code or not state:
        return _login_error_redirect("google_cancelled")
    try:
        stored = verify_payload(
            request.cookies.get(OAUTH_COOKIE, ""), settings.secret_key.get_secret_value()
        )
    except ValueError:
        return _login_error_redirect("state_expired")
    if stored.get("state") != state:
        return _login_error_redirect("state_mismatch")

    try:
        async with httpx.AsyncClient() as http:
            tokens = await google.exchange_code(
                settings, code=code, code_verifier=str(stored["verifier"]), client=http
            )
        identity = google.identity_from_id_token(
            str(tokens.get("id_token", "")),
            client_id=settings.google_client_id,
            nonce=str(stored["nonce"]),
        )
    except google.GoogleAuthError as exc:
        return _login_error_redirect(exc.code)

    if not service.is_email_allowed(identity.email, settings):
        return _login_error_redirect("not_allowed")

    user = await service.login_with_identity(
        session,
        provider="google",
        subject=identity.subject,
        email=identity.email,
        display_name=identity.name,
        settings=settings,
    )
    token, _session = await service.create_session(
        session, user=user, client="web", request=request, settings=settings
    )
    response = RedirectResponse(_safe_next(str(stored.get("next"))), status_code=303)
    _set_session_cookie(response, token, settings)
    response.delete_cookie(OAUTH_COOKIE, path=OAUTH_COOKIE_PATH)
    return response


@auth_router.post("/dev/login", response_model=UserOut)
async def dev_login(
    payload: DevLoginIn,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    _: AuthRateLimit,
) -> UserOut:
    """Local development sign-in. Disabled (404) in production."""
    if not settings.dev_login_allowed:
        raise NotFound()
    if not settings.allowed_login_emails:
        raise Forbidden("Set ALLOWED_LOGIN_EMAILS in backend/.env first.", code="no_allowlist")
    email = (payload.email or settings.allowed_login_emails[0]).lower()
    if not service.is_email_allowed(email, settings):
        raise Forbidden("This email is not on the sign-in allowlist.", code="not_allowed")
    user = await service.login_with_identity(
        session,
        provider="dev",
        subject=email,
        email=email,
        display_name=email.split("@")[0],
        settings=settings,
    )
    token, _session = await service.create_session(
        session, user=user, client="web", request=request, settings=settings
    )
    _set_session_cookie(response, token, settings)
    return UserOut.model_validate(user)


@auth_router.post("/logout", status_code=204)
async def logout(
    auth: CurrentAuth, request: Request, session: SessionDep, settings: SettingsDep
) -> Response:
    await service.revoke_session(
        session, user_id=auth.user.id, session_id=auth.session.id, reason="logout", request=request
    )
    response = Response(status_code=204)
    response.delete_cookie(settings.session_cookie_name, path="/")
    return response


@auth_router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(auth: CurrentAuth, session: SessionDep) -> list[SessionOut]:
    rows = await service.list_sessions(session, auth.user.id)
    return [
        SessionOut.model_validate(row).model_copy(update={"current": row.id == auth.session.id})
        for row in rows
    ]


@auth_router.delete("/sessions/{session_id}", status_code=204)
async def revoke_session(
    session_id: uuid.UUID, auth: CurrentAuth, request: Request, session: SessionDep
) -> Response:
    await service.revoke_session(
        session, user_id=auth.user.id, session_id=session_id, reason="user_revoked", request=request
    )
    return Response(status_code=204)


# ------------------------------------------------------------------ account


@users_router.get("", response_model=MeOut)
async def get_me(auth: CurrentAuth, session: SessionDep) -> MeOut:
    preferences, _version = await service.get_preferences(session, auth.user.id)
    return MeOut(user=UserOut.model_validate(auth.user), preferences=preferences)


@users_router.patch("", response_model=UserOut)
async def update_me(payload: UserUpdate, auth: CurrentAuth, session: SessionDep) -> UserOut:
    user = await service.update_profile(session, auth.user, payload)
    return UserOut.model_validate(user)


@users_router.get("/settings", response_model=SettingsOut)
async def get_settings_endpoint(auth: CurrentAuth, session: SessionDep) -> SettingsOut:
    preferences, version = await service.get_preferences(session, auth.user.id)
    return SettingsOut(preferences=preferences, version=version)


@users_router.patch("/settings", response_model=SettingsOut)
async def update_settings_endpoint(
    payload: PreferencesUpdate, auth: CurrentAuth, session: SessionDep
) -> SettingsOut:
    preferences, version = await service.update_preferences(session, auth.user.id, payload)
    return SettingsOut(preferences=preferences, version=version)


@users_router.get("/consents", response_model=list[ConsentOut])
async def list_consents(auth: CurrentAuth, session: SessionDep) -> list[ConsentOut]:
    return await service.list_consents(session, auth.user.id)


@users_router.put("/consents/{category}", response_model=ConsentOut)
async def set_consent(
    category: ConsentCategory,
    payload: ConsentUpdate,
    auth: CurrentAuth,
    request: Request,
    session: SessionDep,
) -> ConsentOut:
    return await service.set_consent(
        session, user_id=auth.user.id, category=category, granted=payload.granted, request=request
    )
