"""
SyncContainer - DI контейнер для Sync сервиса.

Наследуется от BaseContainer для получения user_repository, company_repository и других базовых сервисов.
Добавляет Sync-специфичные репозитории (SQLAlchemy реляционные).
"""

import logging
from typing import Optional

from core.container import BaseContainer, lazy

logger = logging.getLogger(__name__)


class SyncContainer(BaseContainer):
    """
    Контейнер для Sync сервиса.

    Наследуется от BaseContainer для получения:
    - user_repository, company_repository (из shared БД)
    - auth_service, variables_service

    Добавляет Sync-специфичные:
    - SyncDatabase для реляционных данных
    - Репозитории для spaces, channels, threads, messages, files, git
    """

    def __init__(self, db_url: str, shared_db_url: Optional[str] = None):
        super().__init__(db_url=db_url, shared_db_url=shared_db_url)
        self._sync_db_url = db_url

    # === Sync Database ===

    @lazy
    def sync_db(self):
        from apps.sync.db.base import SyncDatabase
        return SyncDatabase(self._sync_db_url)

    # === Репозитории (sync_db - реляционные) ===

    @lazy
    def space_repository(self):
        from apps.sync.db.repositories.space_repository import SpaceRepository
        return SpaceRepository(db=self.sync_db)

    @lazy
    def channel_repository(self):
        from apps.sync.db.repositories.channel_repository import ChannelRepository
        return ChannelRepository(db=self.sync_db)

    @lazy
    def thread_repository(self):
        from apps.sync.db.repositories.thread_repository import ThreadRepository
        return ThreadRepository(db=self.sync_db)

    @lazy
    def message_repository(self):
        from apps.sync.db.repositories.message_repository import MessageRepository
        return MessageRepository(db=self.sync_db)

    @lazy
    def file_repository(self):
        from apps.sync.db.repositories.file_repository import FileRepository
        return FileRepository(db=self.sync_db)

    @lazy
    def git_resource_ref_repository(self):
        from apps.sync.db.repositories.git_resource_ref_repository import GitResourceRefRepository
        return GitResourceRefRepository(db=self.sync_db)


# === Глобальный контейнер ===

_sync_container: Optional[SyncContainer] = None


def get_sync_container() -> SyncContainer:
    """Получает контейнер (создает при первом вызове)"""
    global _sync_container
    if _sync_container is None:
        from core.config import get_settings
        settings = get_settings()

        if not settings.database.sync_url:
            raise ValueError("database.sync_url не задан")
        sync_db_url = settings.database.sync_url

        _sync_container = SyncContainer(
            db_url=sync_db_url,
            shared_db_url=settings.database.shared_url,
        )
        logger.info(f"SyncContainer инициализирован с БД: {sync_db_url[:50]}...")
    return _sync_container


def set_sync_container(container: SyncContainer):
    """Устанавливает контейнер (для тестов)"""
    global _sync_container
    _sync_container = container


def reset_sync_container():
    """Сбрасывает контейнер (для тестов)"""
    global _sync_container
    _sync_container = None


get_container = get_sync_container
