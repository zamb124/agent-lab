"""Репозиторий для работы с Git-ресурсами (SQLAlchemy)."""

from core.logging import get_logger
from typing import Type

from apps.sync.db.base import BaseSyncRepository, SyncDatabase
from apps.sync.db.models import SyncGitResourceRef

logger = get_logger(__name__)
class GitResourceRefRepository(BaseSyncRepository[SyncGitResourceRef]):
    """Репозиторий для Git-ресурсов с изоляцией по company_id."""

    def __init__(self, db: SyncDatabase):
        super().__init__(db=db)

    @property
    def model_class(self) -> Type[SyncGitResourceRef]:
        return SyncGitResourceRef

    @property
    def id_field(self) -> str:
        return "git_ref_id"
