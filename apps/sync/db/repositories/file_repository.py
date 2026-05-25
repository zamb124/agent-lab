"""Репозиторий для работы с файлами (SQLAlchemy)."""


from typing import override

from sqlalchemy.orm.attributes import InstrumentedAttribute

from apps.sync.db.base import BaseSyncRepository, SyncDatabase
from apps.sync.db.models import SyncFile
from core.logging import get_logger

logger = get_logger(__name__)


class SyncFileRepository(BaseSyncRepository[SyncFile]):
    """Репозиторий для SyncFile-записей с изоляцией по company_id."""

    def __init__(self, db: SyncDatabase) -> None:
        super().__init__(db=db)

    @property
    @override
    def model_class(self) -> type[SyncFile]:
        return SyncFile

    @property
    @override
    def id_column(self) -> InstrumentedAttribute[str]:
        return SyncFile.file_id

    @property
    @override
    def company_id_column(self) -> InstrumentedAttribute[str]:
        return SyncFile.company_id
