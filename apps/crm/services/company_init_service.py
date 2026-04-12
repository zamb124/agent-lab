"""
Сервис инициализации компании.

Копирует системные типы из шаблонов с company_id новой компании.
Автосоздает системные CRM-сущности (company, default namespace).
"""

from typing import List
from datetime import datetime, timezone
import uuid

from sqlalchemy import select

from apps.crm.constants_graph import (
    BELONGS_TO_RELATIONSHIP_TYPE,
    COMPANY_ENTITY_TYPE,
    NAMESPACE_ENTITY_TYPE,
    PLATFORM_COMPANY_ID_ATTR,
    PLATFORM_NAMESPACE_ATTR,
)
from apps.crm.db.models import CRMEntity, EntityType, Relationship, RelationshipType
from apps.crm.db.repositories.entity_repository import EntityRepository
from apps.crm.db.repositories.entity_type_repository import EntityTypeRepository
from apps.crm.db.repositories.namespace_template_repository import NamespaceTemplateRepository
from apps.crm.db.repositories.relationship_repository import RelationshipRepository
from apps.crm.db.repositories.relationship_type_repository import RelationshipTypeRepository
from apps.crm.system_templates import (
    NAMESPACE_TEMPLATE_SEEDS,
    SYSTEM_ENTITY_TYPE_TEMPLATES,
    SYSTEM_RELATIONSHIP_TYPE_TEMPLATES
)
from core.db.repositories.company_repository import CompanyRepository
from core.logging import get_logger

logger = get_logger(__name__)


class CompanyInitService:
    """
    Сервис для инициализации компании в CRM.
    
    При первом входе компании:
    1. Копирует системные типы сущностей
    2. Копирует системные типы связей
    3. Создает системные CRM-сущности (company entity, default namespace entity)
    """
    
    def __init__(
        self,
        entity_type_repo: EntityTypeRepository,
        relationship_type_repo: RelationshipTypeRepository,
        namespace_template_repo: NamespaceTemplateRepository,
        entity_repo: EntityRepository,
        company_repo: CompanyRepository,
        relationship_repo: RelationshipRepository,
    ):
        self._entity_type_repo = entity_type_repo
        self._relationship_type_repo = relationship_type_repo
        self._namespace_template_repo = namespace_template_repo
        self._entity_repo = entity_repo
        self._company_repo = company_repo
        self._relationship_repo = relationship_repo
    
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
        await self._ensure_company_entity(company_id)
        await self._ensure_namespace_entity(company_id, "default")
        
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
            namespace_ids = template.get("namespace_ids", ["default"])
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
                    namespace_ids=namespace_ids,
                    is_context_anchor=template.get('is_context_anchor', False),
                    is_voice_target=template.get('is_voice_target', False),
                    extractable=template.get('extractable', True),
                    created_at=datetime.now(timezone.utc)
                )
                await self._entity_type_repo.update(entity_type)
                created_count += 1
                continue
            await self._entity_type_repo.update_metadata(
                existing.type_id,
                company_id=company_id,
                parent_type_id=template.get("parent_type_id"),
                name=template["name"],
                description=template.get("description"),
                prompt=template.get("prompt"),
                required_fields=template.get("required_fields", {}),
                optional_fields=template.get("optional_fields", {}),
                icon=template.get("icon"),
                color=template.get("color"),
                is_system=True,
                is_event=template.get("is_event", False),
                check_duplicates=template.get("check_duplicates", True),
                weight_coefficient=template.get("weight_coefficient", 1.0),
                is_context_anchor=template.get("is_context_anchor", False),
                is_voice_target=template.get("is_voice_target", False),
                extractable=template.get("extractable", True),
                namespace_ids=namespace_ids,
            )
        
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
                await self._relationship_type_repo.update(rel_type)
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
                    is_context_anchor=item.get("is_context_anchor", False),
                    is_voice_target=item.get("is_voice_target", False),
                )
        return created_count
    
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

    async def _ensure_company_entity(self, company_id: str) -> str:
        """Идемпотентно создает CRM-сущность для компании-тенанта."""
        existing = await self._entity_repo.find_by_attribute(
            entity_type=COMPANY_ENTITY_TYPE,
            attribute_key=PLATFORM_COMPANY_ID_ATTR,
            attribute_value=company_id,
            company_id=company_id,
        )
        if existing:
            return existing[0].entity_id

        company = await self._company_repo.get(company_id)
        if company is None:
            raise ValueError(f"Company not found: {company_id}")

        entity = CRMEntity(
            entity_id=str(uuid.uuid4()),
            company_id=company_id,
            namespace="default",
            entity_type=COMPANY_ENTITY_TYPE,
            name=company.name,
            attributes={PLATFORM_COMPANY_ID_ATTR: company_id},
            tags=[],
            user_id=company.owner_user_id or company_id,
        )
        await self._entity_repo.create(entity)
        logger.info(f"Created company entity {entity.entity_id} for company {company_id}")
        return entity.entity_id

    async def _ensure_namespace_entity(
        self,
        company_id: str,
        namespace_name: str,
    ) -> str:
        """Идемпотентно создает CRM-сущность для namespace."""
        existing = await self._entity_repo.find_by_attribute(
            entity_type=NAMESPACE_ENTITY_TYPE,
            attribute_key=PLATFORM_NAMESPACE_ATTR,
            attribute_value=namespace_name,
            company_id=company_id,
        )
        if existing:
            return existing[0].entity_id

        company_entity_id = await self._ensure_company_entity(company_id)

        entity = CRMEntity(
            entity_id=str(uuid.uuid4()),
            company_id=company_id,
            namespace=namespace_name,
            entity_type=NAMESPACE_ENTITY_TYPE,
            name=namespace_name,
            attributes={PLATFORM_NAMESPACE_ATTR: namespace_name},
            tags=[],
            user_id=company_id,
        )
        await self._entity_repo.create(entity)

        rel = Relationship(
            relationship_id=str(uuid.uuid4()),
            company_id=company_id,
            namespace=namespace_name,
            source_entity_id=entity.entity_id,
            target_entity_id=company_entity_id,
            relationship_type=BELONGS_TO_RELATIONSHIP_TYPE,
        )
        await self._relationship_repo.create(rel)

        logger.info(f"Created namespace entity {entity.entity_id} for namespace {namespace_name}")
        return entity.entity_id
