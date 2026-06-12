"""Database access for search service."""

from __future__ import annotations

from typing import ClassVar

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.config import get_settings


class SearchDatabase:
    """Async PostgreSQL session factory for platform_search."""

    _instance: ClassVar[SearchDatabase | None] = None

    def __init__(self, db_url: str) -> None:
        self._engine: AsyncEngine = create_async_engine(
            db_url,
            echo=False,
            pool_size=5,
            max_overflow=10,
        )
        self._session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @classmethod
    def get_instance(cls, db_url: str | None = None) -> SearchDatabase:
        if cls._instance is None:
            if db_url is None:
                db_url = get_settings().database.search_url
                if not db_url:
                    raise ValueError("database.search_url is required")
            cls._instance = cls(db_url)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    def session(self) -> AsyncSession:
        return self._session_factory()
