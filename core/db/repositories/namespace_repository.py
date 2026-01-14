"""
Репозиторий для работы с Namespace.
is_global=False - namespace изолированы по компаниям через BaseRepository.
"""

from typing import List

from core.db.base_repository import BaseRepository
from core.db.storage import Storage
from core.models.identity_models import Namespace


class NamespaceRepository(BaseRepository[Namespace]):
    """
    Репозиторий для работы с namespace.
    is_global=False - ключи автоматически получают префикс company:{subdomain}:
    """
    
    is_global = False

    def __init__(self, storage: Storage):
        super().__init__(storage=storage, model_class=Namespace)

    def _get_key(self, namespace_name: str) -> str:
        """Ключ: namespace:{name}"""
        return f"namespace:{namespace_name}"

    def _get_prefix(self) -> str:
        """Префикс для списка"""
        return "namespace:"

    def _get_table_name(self) -> str:
        """Таблица в БД"""
        return "namespaces"

    def _extract_entity_id(self, entity: Namespace) -> str:
        """ID = name"""
        return entity.name
    
    async def list_all(self, limit: int = 100) -> List[Namespace]:
        """
        Возвращает все namespace компании.
        Если пусто - создает default.
        """
        namespaces = await super().list_all(limit)
        
        if not namespaces:
            namespaces = [await self._create_default()]
        
        return namespaces
    
    async def list_by_company(self, company_id: str) -> List[Namespace]:
        """Алиас для list_all - компания берется из контекста"""
        return await self.list_all()

    async def _create_default(self) -> Namespace:
        """Создает default namespace для текущей компании"""
        from core.context import get_context
        
        context = get_context()
        company_id = context.active_company.company_id
        
        namespace = Namespace(
            name="default",
            company_id=company_id,
            description="Основное пространство",
            is_default=True,
        )
        
        await self.set(namespace)
        return namespace
