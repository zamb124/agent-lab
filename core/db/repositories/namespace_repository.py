"""
Репозиторий для работы с Namespace.
is_global=False - namespace изолированы по компаниям через BaseRepository.
"""

from __future__ import annotations

from typing import ClassVar, override

from core.context import require_active_company
from core.db.base_repository import BaseRepository
from core.db.storage import Storage
from core.models.identity_models import Namespace


class NamespaceRepository(BaseRepository[Namespace]):
    """
    Репозиторий для работы с namespace.
    is_global=False - ключи автоматически получают префикс company:{subdomain}:
    """

    is_global: ClassVar[bool] = False

    @override
    def __init__(self, storage: Storage):
        super().__init__(storage=storage, model_class=Namespace)

    @override
    def _get_key(self, namespace_name: str) -> str:
        """Ключ: namespace:{name}"""
        return f"namespace:{namespace_name}"

    @override
    def _get_prefix(self) -> str:
        """Префикс для списка"""
        return "namespace:"

    @override
    def _get_table_name(self) -> str:
        """Таблица в БД"""
        return "namespaces"

    @override
    def _extract_entity_id(self, entity: Namespace) -> str:
        """ID = name"""
        return entity.name

    async def list_by_company(
        self, company_id: str, *, limit: int = 200, offset: int = 0
    ) -> list[Namespace]:
        """Список namespace компании; company_id обязан совпадать с активной."""
        active_company_id = require_active_company().company_id
        if company_id != active_company_id:
            raise ValueError('company_id does not match the active company')
        return await self.list(limit=limit, offset=offset)
