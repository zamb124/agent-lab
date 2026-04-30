"""Репозиторий для работы с файлами (SQLAlchemy)."""

from core.logging import get_logger
from typing import Type

from apps.sync.db.base import BaseSyncRepository, SyncDatabase
from apps.sync.db.models import SyncFile

logger = get_logger(__name__)
class SyncFileRepository(BaseSyncRepository[SyncFile]):
    """Репозиторий для SyncFile-записей с изоляцией по company_id."""

    def __init__(self, db: SyncDatabase):
        super().__init__(db=db)

    @property
    def model_class(self) -> Type[SyncFile]:
        return SyncFile

    @property
    def id_field(self) -> str:
        return "file_id"
