"""
Подключение к БД office (Alembic: migrations/office).
"""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


class OfficeDatabase:
    """Engine и фабрика сессий для platform_office."""

    _instance: Optional["OfficeDatabase"] = None

    def __init__(self, db_url: str) -> None:
        self._engine = create_async_engine(
            db_url,
            echo=False,
            pool_size=5,
            max_overflow=10,
        )
        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @classmethod
    def get_instance(cls, db_url: Optional[str] = None) -> "OfficeDatabase":
        if cls._instance is None:
            if db_url is None:
                from core.config import get_settings

                settings = get_settings()
                db_url = settings.database.office_url
                if not db_url:
                    raise ValueError("database.office_url не задан")
            cls._instance = cls(db_url)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    def session(self) -> AsyncSession:
        return self._session_factory()
