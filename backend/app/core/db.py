"""Database engine, session factory and declarative base classes.

Services own transaction boundaries: they call `await session.commit()` when a unit of
work succeeds. The request-scoped session rolls back anything left uncommitted.
"""

import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from functools import lru_cache

from sqlalchemy import DateTime, ForeignKey, MetaData
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

from app.core.config import get_settings
from app.core.ids import uuid7
from app.core.time import utc_now

# Stable constraint names make Alembic autogenerate deterministic.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {datetime: DateTime(timezone=True)}


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)


class TimestampMixin:
    # Python-side defaults: values are known after flush without an extra round trip,
    # which matters in async code where implicit lazy loads are not allowed.
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now)


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(default=None)


class VersionMixin:
    """Optimistic-concurrency counter; clients send it back on updates."""

    version: Mapped[int] = mapped_column(default=1)


class OwnedMixin:
    """Every user-owned row carries `user_id`; deleting the user deletes the row."""

    @declared_attr
    def user_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(ForeignKey("users.id", ondelete="CASCADE"))


@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
    )


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session


SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


def get_session_factory() -> SessionFactory:
    """Sessions for work that outlives the request, such as a streaming response."""
    return get_sessionmaker()
