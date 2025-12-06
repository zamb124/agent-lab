"""
RelationshipService - управление связями между сущностями CRM.
"""

import logging
import uuid
from typing import List, Optional
from datetime import datetime, timezone

from core.context import get_context
from apps.crm.db.models import Relationship
from apps.crm.db.repositories.relationship_repository import RelationshipRepository
from apps.crm.services.entity_service import EntityService
from apps.crm.models.relationship_models import RelationshipCreate, RelationshipResponse

logger = logging.getLogger(__name__)


class RelationshipService:
    """
    Сервис для работы со связями между сущностями.
    
    Связи хранятся в PostgreSQL для эффективных запросов:
    - Поиск связей сущности
    - Построение графа связей
    - Удаление связей при удалении сущности
    """
    
    def __init__(
        self,
        relationship_repository: RelationshipRepository,
        entity_service: EntityService,
    ):
        self._repo = relationship_repository
        self._entity_service = entity_service
    
    def _get_company_id(self) -> str:
        """Получает company_id из контекста"""
        context = get_context()
        if not context or not context.active_company:
            raise ValueError("Нет активной компании в контексте")
        return context.active_company.company_id
    
    async def create_relationship(
        self, 
        data: RelationshipCreate,
        company_id: Optional[str] = None
    ) -> RelationshipResponse:
        """Создает связь между сущностями"""
        company_id = company_id or self._get_company_id()
        
        source = await self._entity_service.get_entity(data.source_entity_id, company_id)
        if not source:
            raise ValueError(f"Сущность {data.source_entity_id} не найдена")
        
        target = await self._entity_service.get_entity(data.target_entity_id, company_id)
        if not target:
            raise ValueError(f"Сущность {data.target_entity_id} не найдена")
        
        relationship = Relationship(
            relationship_id=str(uuid.uuid4()),
            company_id=company_id,
            source_entity_id=data.source_entity_id,
            target_entity_id=data.target_entity_id,
            relationship_type=data.relationship_type,
            weight=data.weight,
            attributes=data.attributes,
            created_at=datetime.now(timezone.utc),
        )
        
        await self._repo.create(relationship)
        logger.info(
            f"Создана связь: {data.source_entity_id} --{data.relationship_type}--> {data.target_entity_id}"
        )
        
        return self._to_response(relationship)
    
    async def get_or_create_relationship(
        self,
        data: RelationshipCreate,
        company_id: Optional[str] = None
    ) -> tuple[RelationshipResponse, bool]:
        """
        Получает существующую связь или создает новую.
        
        Returns:
            (relationship, created) - связь и флаг была ли создана
        """
        company_id = company_id or self._get_company_id()
        
        # Проверяем существует ли уже такая связь
        existing = await self._repo.find_exact(
            company_id=company_id,
            source_entity_id=data.source_entity_id,
            target_entity_id=data.target_entity_id,
            relationship_type=data.relationship_type,
        )
        
        if existing:
            logger.debug(
                f"Связь уже существует: {data.source_entity_id} --{data.relationship_type}--> {data.target_entity_id}"
            )
            return self._to_response(existing), False
        
        # Создаем новую
        created = await self.create_relationship(data, company_id)
        return created, True
    
    async def get_relationship(
        self, 
        relationship_id: str,
        company_id: Optional[str] = None
    ) -> Optional[RelationshipResponse]:
        """Получает связь по ID"""
        relationship = await self._repo.get(relationship_id)
        if not relationship:
            return None
        return self._to_response(relationship)
    
    async def delete_relationship(
        self, 
        relationship_id: str,
        company_id: Optional[str] = None
    ) -> bool:
        """Удаляет связь"""
        success = await self._repo.delete(relationship_id)
        if success:
            logger.info(f"Удалена связь: {relationship_id}")
        return success
    
    async def get_entity_relationships(
        self, 
        entity_id: str,
        company_id: Optional[str] = None,
        include_entities: bool = False
    ) -> List[RelationshipResponse]:
        """Получает все связи сущности"""
        company_id = company_id or self._get_company_id()
        
        relationships = await self._repo.get_by_entity(company_id, entity_id)
        
        responses = []
        for rel in relationships:
            response = self._to_response(rel)
            
            if include_entities:
                source = await self._entity_service.get_entity(rel.source_entity_id, company_id)
                target = await self._entity_service.get_entity(rel.target_entity_id, company_id)
                
                if source:
                    response.source_entity = {
                        "entity_id": source.entity_id,
                        "type": source.type,
                        "name": source.name,
                    }
                if target:
                    response.target_entity = {
                        "entity_id": target.entity_id,
                        "type": target.type,
                        "name": target.name,
                    }
            
            responses.append(response)
        
        return responses
    
    async def get_relationships_between(
        self, 
        entity_id_1: str,
        entity_id_2: str,
        company_id: Optional[str] = None
    ) -> List[RelationshipResponse]:
        """Получает связи между двумя сущностями"""
        company_id = company_id or self._get_company_id()
        
        relationships = await self._repo.get_between(company_id, entity_id_1, entity_id_2)
        return [self._to_response(rel) for rel in relationships]
    
    async def list_relationships(
        self,
        relationship_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        company_id: Optional[str] = None
    ) -> List[RelationshipResponse]:
        """Получает список связей с фильтрацией"""
        company_id = company_id or self._get_company_id()
        
        if relationship_type:
            relationships = await self._repo.get_by_type(company_id, relationship_type)
        else:
            relationships = await self._repo.get_by_company(company_id, limit, offset)
        
        return [self._to_response(rel) for rel in relationships]
    
    def _to_response(self, relationship: Relationship) -> RelationshipResponse:
        """Конвертирует модель в response"""
        return RelationshipResponse(
            relationship_id=relationship.relationship_id,
            company_id=relationship.company_id,
            source_entity_id=relationship.source_entity_id,
            target_entity_id=relationship.target_entity_id,
            relationship_type=relationship.relationship_type,
            weight=relationship.weight,
            attributes=relationship.attributes or {},
            created_at=relationship.created_at,
        )



