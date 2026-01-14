"""
Репозиторий для entities в ChromaDB.

Хелперы для удобной работы с типами.
"""

from typing import List, Optional, Dict, Any

from apps.crm.db.chroma_repository import BaseCRMChromaRepository
from apps.crm.models.entity import ChromaDBEntity


class EntityChromaRepository(BaseCRMChromaRepository):
    """
    Репозиторий для entities в ChromaDB.
    
    Предоставляет удобные методы для работы с типами.
    """
    
    async def get_notes(
        self,
        note_subtype: Optional[str] = None,
        namespace: Optional[str] = None,
        filters: Optional[Dict] = None,
        limit: int = 100,
        company_id: Optional[str] = None
    ) -> List[ChromaDBEntity]:
        """Получает заметки"""
        return await self.list_all(
            entity_type="note",
            entity_subtype=note_subtype,
            namespace=namespace,
            filters=filters,
            limit=limit,
            company_id=company_id
        )
    
    async def search_notes(
        self,
        query: str,
        note_subtype: Optional[str] = None,
        namespace: Optional[str] = None,
        limit: int = 10,
        company_id: Optional[str] = None
    ) -> List[ChromaDBEntity]:
        """Семантический поиск по заметкам"""
        return await self.search(
            query=query,
            entity_type="note",
            entity_subtype=note_subtype,
            namespace=namespace,
            limit=limit,
            company_id=company_id
        )
    
    async def get_tasks(
        self,
        namespace: Optional[str] = None,
        filters: Optional[Dict] = None,
        limit: int = 100,
        company_id: Optional[str] = None
    ) -> List[ChromaDBEntity]:
        """Получает задачи"""
        return await self.list_all(
            entity_type="task",
            namespace=namespace,
            filters=filters,
            limit=limit,
            company_id=company_id
        )
    
    async def search_tasks(
        self,
        query: str,
        namespace: Optional[str] = None,
        limit: int = 10,
        company_id: Optional[str] = None
    ) -> List[ChromaDBEntity]:
        """Семантический поиск по задачам"""
        return await self.search(
            query=query,
            entity_type="task",
            namespace=namespace,
            limit=limit,
            company_id=company_id
        )
    
    async def get_by_type(
        self,
        entity_type: str,
        entity_subtype: Optional[str] = None,
        namespace: Optional[str] = None,
        filters: Optional[Dict] = None,
        limit: int = 100,
        company_id: Optional[str] = None
    ) -> List[ChromaDBEntity]:
        """Получает entities по типу"""
        return await self.list_all(
            entity_type=entity_type,
            entity_subtype=entity_subtype,
            namespace=namespace,
            filters=filters,
            limit=limit,
            company_id=company_id
        )
    
    async def search_by_type(
        self,
        query: str,
        entity_type: str,
        entity_subtype: Optional[str] = None,
        namespace: Optional[str] = None,
        limit: int = 10,
        company_id: Optional[str] = None
    ) -> List[ChromaDBEntity]:
        """Семантический поиск по типу"""
        return await self.search(
            query=query,
            entity_type=entity_type,
            entity_subtype=entity_subtype,
            namespace=namespace,
            limit=limit,
            company_id=company_id
        )
    
    async def get_by_tag(
        self,
        tag: str,
        entity_type: Optional[str] = None,
        namespace: Optional[str] = None,
        limit: int = 100,
        company_id: Optional[str] = None
    ) -> List[ChromaDBEntity]:
        """Получает entities по тегу"""
        filters = {"tags": {"$contains": tag}}
        return await self.list_all(
            entity_type=entity_type,
            namespace=namespace,
            filters=filters,
            limit=limit,
            company_id=company_id
        )
