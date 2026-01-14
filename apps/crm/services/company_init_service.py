"""
Сервис инициализации компании.

Копирует системные типы из шаблонов с company_id новой компании.
"""

from typing import List
from datetime import datetime, timezone

from apps.crm.db.models import EntityType, RelationshipType
from apps.crm.db.repositories.entity_type_repository import EntityTypeRepository
from apps.crm.db.repositories.relationship_type_repository import RelationshipTypeRepository
from apps.crm.system_templates import (
    SYSTEM_ENTITY_TYPE_TEMPLATES,
    SYSTEM_RELATIONSHIP_TYPE_TEMPLATES
)
from core.logging import get_logger

logger = get_logger(__name__)


class CompanyInitService:
    """
    Сервис для инициализации компании в CRM.
    
    При первом входе компании:
    1. Копирует системные типы сущностей (note, meeting, call, task)
    2. Копирует системные типы связей (mentions, linked)
    """
    
    def __init__(
        self,
        entity_type_repo: EntityTypeRepository,
        relationship_type_repo: RelationshipTypeRepository,
    ):
        self._entity_type_repo = entity_type_repo
        self._relationship_type_repo = relationship_type_repo
    
    async def initialize_company(self, company_id: str) -> dict:
        """
        Инициализирует компанию: копирует системные типы с company_id.
        
        Args:
            company_id: ID компании для инициализации
        
        Returns:
            Статистика: сколько типов создано
        """
        logger.info(f"Initializing company: {company_id}")
        
        existing_entity_types = await self._check_existing_types(company_id)
        
        if existing_entity_types:
            logger.info(f"Company {company_id} already initialized ({len(existing_entity_types)} types)")
            return {
                "entity_types": len(existing_entity_types),
                "relationship_types": 0,
                "already_initialized": True
            }
        
        entity_types_created = await self._init_entity_types(company_id)
        relationship_types_created = await self._init_relationship_types(company_id)
        
        logger.info(
            f"Company {company_id} initialized: "
            f"{entity_types_created} entity types, "
            f"{relationship_types_created} relationship types"
        )
        
        return {
            "entity_types": entity_types_created,
            "relationship_types": relationship_types_created,
            "already_initialized": False
        }
    
    async def _init_entity_types(self, company_id: str) -> int:
        """Создает системные типы сущностей для компании"""
        created_count = 0
        
        for template in SYSTEM_ENTITY_TYPE_TEMPLATES:
            entity_type = EntityType(
                type_id=template['type_id'],
                company_id=company_id,
                parent_type_id=template.get('parent_type_id'),
                name=template['name'],
                description=template.get('description'),
                prompt=template.get('prompt'),
                required_fields=template.get('required_fields', {}),
                optional_fields=template.get('optional_fields', {}),
                icon=template.get('icon'),
                color=template.get('color'),
                is_system=True,
                is_event=template.get('is_event', False),
                check_duplicates=template.get('check_duplicates', True),
                weight_coefficient=template.get('weight_coefficient', 1.0),
                created_at=datetime.now(timezone.utc)
            )
            
            try:
                await self._entity_type_repo.create(entity_type)
                created_count += 1
                logger.debug(f"Created entity type: {entity_type.type_id}")
            except Exception as e:
                logger.error(f"Failed to create entity type {entity_type.type_id}: {e}")
        
        return created_count

    async def _init_relationship_types(self, company_id: str) -> int:
        """Создает системные типы связей для компании"""
        created_count = 0
        
        for template in SYSTEM_RELATIONSHIP_TYPE_TEMPLATES:
            rel_type = RelationshipType(
                type_id=template['type_id'],
                company_id=company_id,
                name=template['name'],
                description=template.get('description'),
                prompt=template.get('prompt'),
                is_directed=template.get('is_directed', True),
                inverse_type_id=None,
                icon=template.get('icon'),
                color=template.get('color'),
                is_system=True,
                weight_default=template.get('weight_default', 1.0),
                created_at=datetime.now(timezone.utc)
            )
            
            try:
                await self._relationship_type_repo.create(rel_type)
                created_count += 1
                logger.debug(f"Created relationship type: {rel_type.type_id}")
            except Exception as e:
                logger.error(f"Failed to create relationship type {rel_type.type_id}: {e}")
        
        return created_count
    
    async def is_company_initialized(self, company_id: str) -> bool:
        """Проверяет инициализирована ли компания"""
        types = await self._check_existing_types(company_id)
        return len(types) > 0
    
    async def _check_existing_types(self, company_id: str) -> List[EntityType]:
        """
        Проверяет существующие типы для компании (прямой запрос к БД).
        
        Args:
            company_id: ID компании
        
        Returns:
            Список существующих типов (системные для проверки инициализации)
        """
        from sqlalchemy import select
        
        async with self._entity_type_repo._db.session() as session:
            stmt = select(EntityType).where(
                EntityType.company_id == company_id,
                EntityType.is_system == True
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
