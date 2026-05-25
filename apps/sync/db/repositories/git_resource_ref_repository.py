"""Репозиторий для работы с Git-ресурсами (SQLAlchemy)."""


from typing import override

from sqlalchemy.orm.attributes import InstrumentedAttribute

from apps.sync.db.base import BaseSyncRepository, SyncDatabase
from apps.sync.db.models import SyncGitResourceRef
from core.logging import get_logger

logger = get_logger(__name__)


class GitResourceRefRepository(BaseSyncRepository[SyncGitResourceRef]):
    """Репозиторий для Git-ресурсов с изоляцией по company_id."""

    def __init__(self, db: SyncDatabase) -> None:
        super().__init__(db=db)

    @property
    @override
    def model_class(self) -> type[SyncGitResourceRef]:
        return SyncGitResourceRef

    @property
    @override
    def id_column(self) -> InstrumentedAttribute[str]:
        return SyncGitResourceRef.git_ref_id

    @property
    @override
    def company_id_column(self) -> InstrumentedAttribute[str]:
        return SyncGitResourceRef.company_id
