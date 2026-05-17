"""
SyncContainer - DI контейнер для Sync сервиса.

Наследуется от BaseContainer для получения user_repository, company_repository и других базовых сервисов.
Добавляет Sync-специфичные репозитории (SQLAlchemy реляционные).
"""

from typing import Optional

from apps.sync.db.base import SyncDatabase
from apps.sync.db.repositories.call_repository import CallRepository
from apps.sync.db.repositories.call_speech_egress_repository import CallSpeechEgressTrackRepository
from apps.sync.db.repositories.channel_repository import ChannelRepository
from apps.sync.db.repositories.file_repository import SyncFileRepository
from apps.sync.db.repositories.git_resource_ref_repository import GitResourceRefRepository
from apps.sync.db.repositories.meeting_repository import CallRecordingRepository
from apps.sync.db.repositories.message_repository import MessageRepository
from apps.sync.db.repositories.thread_repository import ThreadRepository
from core.config import get_settings
from core.container import BaseContainer, lazy
from core.logging import get_logger

logger = get_logger(__name__)
class SyncContainer(BaseContainer):
    """
    Контейнер для Sync сервиса.

    Наследуется от BaseContainer для получения:
    - user_repository, company_repository (из shared БД)
    - auth_service, variables_service

    Добавляет Sync-специфичные:
    - SyncDatabase для реляционных данных
    - Репозитории для channels, threads, messages, files, git
    """

    def __init__(self, db_url: str, shared_db_url: Optional[str] = None):
        super().__init__(db_url=db_url, shared_db_url=shared_db_url)
        self._sync_db_url = db_url

    # === Sync Database ===

    @lazy
    def sync_db(self):
        return SyncDatabase(self._sync_db_url)

    # === Репозитории (sync_db - реляционные) ===

    @lazy
    def channel_repository(self):
        return ChannelRepository(db=self.sync_db)

    @lazy
    def thread_repository(self):
        return ThreadRepository(db=self.sync_db)

    @lazy
    def message_repository(self):
        return MessageRepository(db=self.sync_db)

    @lazy
    def sync_file_repository(self):
        return SyncFileRepository(db=self.sync_db)

    @lazy
    def git_resource_ref_repository(self):
        return GitResourceRefRepository(db=self.sync_db)

    @lazy
    def call_repository(self):
        return CallRepository(db=self.sync_db)

    @lazy
    def call_recording_repository(self):
        return CallRecordingRepository(db=self.sync_db)

    @lazy
    def call_speech_egress_track_repository(self):
        return CallSpeechEgressTrackRepository(db=self.sync_db)

# === Глобальный контейнер ===

_sync_container: Optional[SyncContainer] = None

def get_sync_container() -> SyncContainer:
    """Получает контейнер (создает при первом вызове)"""
    global _sync_container
    if _sync_container is None:
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
