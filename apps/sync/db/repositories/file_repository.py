"""Репозиторий для работы с файлами (SQLAlchemy)."""

import logging
from typing import Type

from apps.sync.db.base import BaseSyncRepository, SyncDatabase
from apps.sync.db.models import SyncFile

logger = logging.getLogger(__name__)


class FileRepository(BaseSyncRepository[SyncFile]):
    """Репозиторий для файлов с изоляцией по company_id."""

    def __init__(self, db: SyncDatabase):
        super().__init__(db=db)

    @property
    def model_class(self) -> Type[SyncFile]:
        return SyncFile

    @property
    def id_field(self) -> str:
        return "file_id"
