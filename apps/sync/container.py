"""
SyncContainer - DI контейнер для Sync сервиса.

Наследуется от BaseContainer для получения user_repository, company_repository и других базовых сервисов.
Добавляет Sync-специфичные репозитории (SQLAlchemy реляционные).
"""


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
from core.container import BaseContainer, ContainerRegistry, lazy
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

    def __init__(self, db_url: str, shared_db_url: str | None = None) -> None:
        super().__init__(db_url=db_url, shared_db_url=shared_db_url)
        self._sync_db_url: str = db_url

    # === Sync Database ===

    @lazy
    def sync_db(self) -> SyncDatabase:
        return SyncDatabase(self._sync_db_url)

    # === Репозитории (sync_db - реляционные) ===

    @lazy
    def channel_repository(self) -> ChannelRepository:
        return ChannelRepository(db=self.sync_db)

    @lazy
    def thread_repository(self) -> ThreadRepository:
        return ThreadRepository(db=self.sync_db)

    @lazy
    def message_repository(self) -> MessageRepository:
        return MessageRepository(db=self.sync_db)

    @lazy
    def sync_file_repository(self) -> SyncFileRepository:
        return SyncFileRepository(db=self.sync_db)

    @lazy
    def git_resource_ref_repository(self) -> GitResourceRefRepository:
        return GitResourceRefRepository(db=self.sync_db)

    @lazy
    def call_repository(self) -> CallRepository:
        return CallRepository(db=self.sync_db)

    @lazy
    def call_recording_repository(self) -> CallRecordingRepository:
        return CallRecordingRepository(db=self.sync_db)

    @lazy
    def call_speech_egress_track_repository(self) -> CallSpeechEgressTrackRepository:
        return CallSpeechEgressTrackRepository(db=self.sync_db)

def _create_sync_container() -> SyncContainer:
    settings = get_settings()
    if not settings.database.sync_url:
        raise ValueError("database.sync_url не задан")
    return SyncContainer(
        db_url=settings.database.sync_url,
        shared_db_url=settings.database.shared_url,
    )


_sync_registry: ContainerRegistry[SyncContainer] = ContainerRegistry(
    _create_sync_container, name="SyncContainer"
)

get_sync_container = _sync_registry.get
set_sync_container = _sync_registry.set
reset_sync_container = _sync_registry.reset
get_container = _sync_registry.get
