"""
Сервис инициализации компании.

Копирует системные типы из шаблонов с company_id новой компании.
"""

from typing import List
from datetime import datetime, timezone

from sqlalchemy import select

from apps.crm.db.models import EntityType, RelationshipType
from apps.crm.db.repositories.entity_type_repository import EntityTypeRepository
from apps.crm.db.repositories.namespace_template_repository import NamespaceTemplateRepository
from apps.crm.db.repositories.relationship_type_repository import RelationshipTypeRepository
from apps.crm.system_templates import (
    NAMESPACE_TEMPLATE_SEEDS,
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
        namespace_template_repo: NamespaceTemplateRepository,
    ):
        self._entity_type_repo = entity_type_repo
        self._relationship_type_repo = relationship_type_repo
        self._namespace_template_repo = namespace_template_repo
    
    async def initialize_company(self, company_id: str) -> dict:
        """
        Инициализирует компанию: копирует системные типы с company_id.
        
        Args:
            company_id: ID компании для инициализации
        
        Returns:
            Статистика: сколько типов создано
        """
        logger.info(f"Initializing company: {company_id}")
        
        entity_types_created = await self._init_entity_types(company_id)
        relationship_types_created = await self._init_relationship_types(company_id)
        templates_created = await self._init_namespace_templates(company_id)
        
        logger.info(
            f"Company {company_id} initialized: "
            f"{entity_types_created} entity types, "
            f"{relationship_types_created} relationship types, "
            f"{templates_created} namespace templates"
        )
        
        return {
            "entity_types": entity_types_created,
            "relationship_types": relationship_types_created,
            "namespace_templates": templates_created,
            "already_initialized": entity_types_created == 0 and relationship_types_created == 0 and templates_created == 0
        }
    
    async def _init_entity_types(self, company_id: str) -> int:
        """Создает или обновляет минимальное системное ядро типов."""
        created_count = 0
        existing_types = await self._check_existing_types(company_id)
        existing_by_id = {item.type_id: item for item in existing_types}

        for template in SYSTEM_ENTITY_TYPE_TEMPLATES:
            existing = existing_by_id.get(template["type_id"])
            if existing is None:
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
                    namespace_ids=["default"],
                    created_at=datetime.now(timezone.utc)
                )
                await self._entity_type_repo.create(entity_type)
                created_count += 1
                continue
            existing.parent_type_id = template.get("parent_type_id")
            existing.name = template["name"]
            existing.description = template.get("description")
            existing.prompt = template.get("prompt")
            existing.required_fields = template.get("required_fields", {})
            existing.optional_fields = template.get("optional_fields", {})
            existing.icon = template.get("icon")
            existing.color = template.get("color")
            existing.is_system = True
            existing.is_event = template.get("is_event", False)
            existing.check_duplicates = template.get("check_duplicates", True)
            existing.weight_coefficient = template.get("weight_coefficient", 1.0)
            if "default" not in existing.namespace_ids:
                existing.namespace_ids = list(existing.namespace_ids) + ["default"]
            await self._entity_type_repo.update(existing)
        
        return created_count

    async def _init_relationship_types(self, company_id: str) -> int:
        """Создает или обновляет минимальное системное ядро связей."""
        created_count = 0
        existing_relationship_types = await self._check_existing_relationship_types(company_id)
        existing_by_id = {item.type_id: item for item in existing_relationship_types}

        for template in SYSTEM_RELATIONSHIP_TYPE_TEMPLATES:
            existing = existing_by_id.get(template["type_id"])
            if existing is None:
                rel_type = RelationshipType(
                    type_id=template['type_id'],
                    company_id=company_id,
                    name=template['name'],
                    description=template.get('description'),
                    prompt=template.get('prompt'),
                    is_directed=template.get('is_directed', True),
                    inverse_type_id=template.get('inverse_type_id'),
                    icon=template.get('icon'),
                    color=template.get('color'),
                    is_system=True,
                    weight_default=template.get('weight_default', 1.0),
                    created_at=datetime.now(timezone.utc)
                )
                await self._relationship_type_repo.create(rel_type)
                created_count += 1
                continue
            existing.name = template["name"]
            existing.description = template.get("description")
            existing.prompt = template.get("prompt")
            existing.is_directed = template.get("is_directed", True)
            existing.inverse_type_id = template.get("inverse_type_id")
            existing.icon = template.get("icon")
            existing.color = template.get("color")
            existing.is_system = True
            existing.weight_default = template.get("weight_default", 1.0)
            await self._relationship_type_repo.update(existing)
        
        return created_count

    async def _init_namespace_templates(self, company_id: str) -> int:
        created_count = 0
        for seed in NAMESPACE_TEMPLATE_SEEDS:
            existing = await self._namespace_template_repo.get_by_template_id(seed["template_id"], company_id=company_id)
            if existing is None:
                existing = await self._namespace_template_repo.create_template(
                    template_id=seed["template_id"],
                    name=seed["name"],
                    description=seed.get("description"),
                    icon=seed.get("icon"),
                    company_id=company_id,
                    is_system=True,
                )
                created_count += 1
            else:
                existing.name = seed["name"]
                existing.description = seed.get("description")
                existing.icon = seed.get("icon")
                existing.is_system = True
                existing = await self._namespace_template_repo.update(existing)

            for item in seed["types"]:
                await self._namespace_template_repo.upsert_type(
                    template_key=existing.template_key,
                    type_id=item["type_id"],
                    parent_type_id=item.get("parent_type_id"),
                    name=item["name"],
                    description=item.get("description"),
                    prompt=item.get("prompt"),
                    required_fields=item.get("required_fields", {}),
                    optional_fields=item.get("optional_fields", {}),
                    icon=item.get("icon"),
                    color=item.get("color"),
                    is_event=item.get("is_event", False),
                    check_duplicates=item.get("check_duplicates", True),
                    weight_coefficient=item.get("weight_coefficient", 1.0),
                    namespace_ids=item.get("namespace_ids", []),
                )
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
            Список существующих типов компании
        """
        async with self._entity_type_repo._db.session() as session:
            stmt = select(EntityType).where(
                EntityType.company_id == company_id
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def _check_existing_relationship_types(self, company_id: str) -> List[RelationshipType]:
        async with self._relationship_type_repo._db.session() as session:
            stmt = select(RelationshipType).where(
                RelationshipType.company_id == company_id,
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
