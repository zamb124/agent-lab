"""
Репозиторий для работы с Company.
Использует shared БД, is_global=True (не изолирован по компаниям).
"""

import logging

from core.db.base_repository import BaseRepository
from core.db.storage import Storage
from core.models.identity_models import Company

logger = logging.getLogger(__name__)


class CompanyRepository(BaseRepository[Company]):
    """
    Репозиторий для работы с компаниями.
    is_global=True - компании не изолированы (это метаданные самих компаний).
    """
    
    is_global = True

    def __init__(self, storage: Storage):
        super().__init__(storage=storage, model_class=Company)

    def _get_key(self, company_id: str) -> str:
        return f"company:{company_id}"

    def _get_prefix(self) -> str:
        return "company:"

    def _get_table_name(self) -> str:
        return "storage"

    def _extract_entity_id(self, entity: Company) -> str:
        return entity.company_id
