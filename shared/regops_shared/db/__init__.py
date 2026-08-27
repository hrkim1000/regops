"""Engines and session factories — async for the API, sync for Celery workers.

FastAPI path operations use the async engine. Celery workers use the **sync** one: a prefork worker
has no long-lived event loop, and an asyncpg connection cached across ``asyncio.run()`` calls is
bound to a loop that has already closed. The sync driver is already a dependency (Alembic needs it),
so this costs nothing beyond one more factory.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from regops_shared.settings import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        echo=settings.db_echo,
        pool_pre_ping=True,
        # asyncpg takes startup parameters under `server_settings`; psycopg2 below takes
        # `application_name` directly. Same destination, two spellings.
        connect_args={"server_settings": {"application_name": settings.service_name}},
    )


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False, autoflush=False)


async def get_db() -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency. The *caller* commits — helpers only ``flush()``."""
    async with get_sessionmaker()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


@lru_cache
def get_sync_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.sync_database_url,
        echo=settings.db_echo,
        pool_pre_ping=True,
        connect_args={"application_name": settings.service_name},
    )


@lru_cache
def get_sync_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(get_sync_engine(), expire_on_commit=False, autoflush=False)


@contextmanager
def sync_session() -> Iterator[Session]:
    """Worker-side session. The *caller* commits, so a pipeline stage can commit incrementally and
    a retry skips the rows already done."""
    session = get_sync_sessionmaker()()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


__all__ = [
    "AsyncSession",
    "Session",
    "get_db",
    "get_engine",
    "get_sessionmaker",
    "get_sync_engine",
    "get_sync_sessionmaker",
    "sync_session",
]
