"""Менеджер подключения к БД `platform_secrets`."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.db.sqlalchemy_pool import sqlalchemy_async_engine_pool_kwargs


class SecretsDatabase:
    """Engine + session factory для версионируемого хранилища переменных."""

    def __init__(self, db_url: str) -> None:
        self._engine: AsyncEngine = create_async_engine(
            db_url,
            echo=False,
            **sqlalchemy_async_engine_pool_kwargs(),
        )
        self._session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    def session(self) -> AsyncSession:
        return self._session_factory()
