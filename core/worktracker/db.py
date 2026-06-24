"""Менеджер подключения к БД `platform_worktracker`."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class WorktrackerDatabase:
    """Engine + session factory для ядра задач."""

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

    def session(self) -> AsyncSession:
        return self._session_factory()
