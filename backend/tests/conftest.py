"""Test setup.

Tests run against a real PostgreSQL database (never SQLite) so constraints, CITEXT, JSONB and
partial indexes behave exactly as in production. The schema is migrated once per session with
Alembic; each test runs inside a transaction that is rolled back afterwards.
"""

import base64
import os
from collections.abc import AsyncIterator
from pathlib import Path

# Settings are read once and cached, so the test environment must be set before app imports.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://localhost:55432/personal_os_test"
)
os.environ.update(
    {
        "ENVIRONMENT": "test",
        "LOG_LEVEL": "WARNING",
        "DATABASE_URL": TEST_DATABASE_URL,
        # Fake, test-only key (allow-listed for the secret scanner on the next line).
        "SECRET_KEY": "test-secret-key-0123456789abcdef0123456789abcdef",  # gitleaks:allow
        "ENCRYPTION_KEYS": "t1:" + base64.b64encode(bytes(range(32))).decode(),
        "ALLOWED_LOGIN_EMAILS": "owner@example.com,second@example.com",
        "DEV_LOGIN_ENABLED": "true",
        "WEB_ORIGIN": "http://localhost:3000",
        "GOOGLE_CLIENT_ID": "test-client.apps.googleusercontent.com",
        "GOOGLE_CLIENT_SECRET": "test-google-secret",
        "ANTHROPIC_API_KEY": "",
    }
)

from contextlib import asynccontextmanager  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import get_session, get_session_factory  # noqa: E402
from app.core.ratelimit import limiter  # noqa: E402
from app.main import create_app  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]
WEB_ORIGIN = "http://localhost:3000"


@pytest.fixture(scope="session")
def migrated_database() -> None:
    engine = create_engine(TEST_DATABASE_URL, poolclass=NullPool)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")


@pytest.fixture
async def db_session(migrated_database: None) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()
    await engine.dispose()


@pytest.fixture
def app(db_session: AsyncSession) -> FastAPI:
    application = create_app(get_settings())

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    @asynccontextmanager
    async def _factory() -> AsyncIterator[AsyncSession]:
        yield db_session

    application.dependency_overrides[get_session] = _session_override
    application.dependency_overrides[get_session_factory] = lambda: _factory
    limiter.reset()
    return application


def make_client(app: FastAPI) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Origin": WEB_ORIGIN},
    )


async def sign_in(client: AsyncClient, email: str) -> dict[str, object]:
    response = await client.post("/api/v1/auth/dev/login", json={"email": email})
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with make_client(app) as http:
        yield http


@pytest.fixture
async def owner(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """A client signed in as the primary user."""
    async with make_client(app) as http:
        await sign_in(http, "owner@example.com")
        yield http


@pytest.fixture
async def intruder(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """A second, separate user. Used to prove one user can never touch another's data."""
    async with make_client(app) as http:
        await sign_in(http, "second@example.com")
        yield http
