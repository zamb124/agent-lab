"""
Сервис инициализации компании.

Копирует системные типы из шаблонов с company_id новой компании.
Автосоздает системные CRM-сущности (company, default namespace).

Все методы _init_* идемпотентны под параллельным вызовом (pytest-xdist):
при конкурентном INSERT дубликат PK/unique воспринимается как успех
(другой worker уже создал запись).
"""

import uuid
from datetime import UTC, datetime

from oxyde.exceptions import UniqueViolationError

from apps.crm.constants_graph import (
    BELONGS_TO_RELATIONSHIP_TYPE,
    COMPANY_ENTITY_TYPE,
    NAMESPACE_ENTITY_TYPE,
    PLATFORM_COMPANY_ID_ATTR,
    PLATFORM_NAMESPACE_ATTR,
)
from apps.crm.db.company_init_lock import crm_company_init_lock
from apps.crm.models.company_mapping import CompanyMapping
from apps.crm.models.crm_entity import CRMEntity, entity_namespace, index_crm_entity
from apps.crm.models.entity_type import EntityType
from apps.crm.models.namespace_template import NamespaceTemplate
from apps.crm.models.namespace_template_type import NamespaceTemplateType
from apps.crm.models.relationship import Relationship
from apps.crm.models.relationship_type import RelationshipType
from apps.crm.services.crm_entity_access_service import CrmEntityAccessService
from apps.crm.system_templates import (
    COMMON_NAMESPACE_ANCHOR_TYPES,
    NAMESPACE_TEMPLATE_SEEDS,
    SYSTEM_ENTITY_TYPE_TEMPLATES,
    SYSTEM_RELATIONSHIP_TYPE_TEMPLATES,
    EntityTypeTemplate,
)
from core.logging import get_logger
from core.models.identity_models import Company, User
from core.namespace import NamespaceService, ensure_personal_namespace_for_user
from core.rag import BaseRAGProvider
from core.types import require_json_object

logger = get_logger(__name__)

RETIRED_NAMESPACE_TEMPLATE_IDS: frozenset[str] = frozenset({"amocrm"})


class CompanyInitService:
    """
    Сервис для инициализации компании в CRM.

    При первом входе компании:
    1. Копирует системные типы сущностей
    2. Копирует системные типы связей
    3. Создает системные CRM-сущности (company entity, default namespace entity)
    4. Гарантирует personal namespace каждому member
    """

    def __init__(
        self,
        rag: BaseRAGProvider,
        namespace_service: NamespaceService,
        entity_access: CrmEntityAccessService,
    ) -> None:
        self._rag: BaseRAGProvider = rag
        self._namespace_service: NamespaceService = namespace_service
        self._entity_access: CrmEntityAccessService = entity_access

    async def initialize_company(self, company_id: str, *, reseed: bool = False) -> dict[str, int | bool]:
        """
        Инициализирует компанию: копирует системные типы с company_id.

        Insert-only по умолчанию: существующие типы/шаблоны/сущности не
        переписываются и не re-sync в OpenFGA. Полный reseed (update_metadata,
        upsert шаблонов, backfill personal namespace, FGA repair) — только
        ``reseed=True`` (lifespan CRM для ``system``).

        Параллельные granian workers и xdist сериализуются Postgres
        ``pg_advisory_lock`` на ``company_id``: иначе N lifespan'ов на пустой
        ``company_mapping`` ловят UniqueViolation и валят ASGI startup.

        Иначе 10 xdist workers на первой волне CRM e2e каждый проходит
        personal namespace всех накопленных ``system.members`` и душит
        Postgres/OpenFGA → ERROR setup ``crm_client``.
        """
        async with crm_company_init_lock(company_id):
            return await self._initialize_company_locked(company_id, reseed=reseed)

    async def _initialize_company_locked(
        self, company_id: str, *, reseed: bool
    ) -> dict[str, int | bool]:
        logger.info("crm.company_init.started", company_id=company_id)

        entity_types_created = await self._init_entity_types(company_id, reseed=reseed)
        relationship_types_created = await self._init_relationship_types(company_id, reseed=reseed)
        templates_created = await self._init_namespace_templates(company_id, reseed=reseed)
        _ = await self._ensure_company_entity(company_id, reseed=reseed)
        _ = await self._ensure_namespace_entity(company_id, "default", reseed=reseed)
        await self._ensure_default_namespace_record(company_id)
        await self._ensure_default_organization_entity(company_id, reseed=reseed)
        created_anything = (
            entity_types_created > 0
            or relationship_types_created > 0
            or templates_created > 0
        )
        personal_ensured = 0
        if reseed or created_anything:
            personal_ensured = await self._ensure_personal_namespaces_for_members(company_id)

        logger.info(
            (
                f"Company {company_id} initialized: {entity_types_created} entity types, "
                f"{relationship_types_created} relationship types, {templates_created} namespace templates, "
                f"{personal_ensured} personal namespaces"
            )
        )

        return {
            "entity_types": entity_types_created,
            "relationship_types": relationship_types_created,
            "namespace_templates": templates_created,
            "personal_namespaces": personal_ensured,
            "already_initialized": entity_types_created == 0
            and relationship_types_created == 0
            and templates_created == 0,
        }

    async def _init_entity_types(self, company_id: str, *, reseed: bool) -> int:
        """Создаёт или обновляет минимальное системное ядро типов в пространстве default.

        Insert-только стратегия: каждая INSERT выполняется атомарно; IntegrityError
        (UniqueViolation) от параллельного xdist worker воспринимается как успех.
        """
        created_count = 0
        init_namespace = "default"
        existing_types = await self._check_existing_types(company_id)
        existing_by_key = {(item.namespace, item.type_id): item for item in existing_types}

        entity_type_seed_specs: tuple[EntityTypeTemplate, ...] = (
            *SYSTEM_ENTITY_TYPE_TEMPLATES,
            *COMMON_NAMESPACE_ANCHOR_TYPES,
        )
        for template in entity_type_seed_specs:
            key = (init_namespace, template["type_id"])
            existing = existing_by_key.get(key)
            if existing is not None:
                if not reseed:
                    continue
                await EntityType.update_field_patch(
                    template["type_id"],
                    namespace=init_namespace,
                    company_id=company_id,
                    patch={
                        "parent_type_id": template.get("parent_type_id"),
                        "name": template["name"],
                        "description": template.get("description"),
                        "prompt": template.get("prompt"),
                        "required_fields": template.get("required_fields", {}),
                        "optional_fields": template.get("optional_fields", {}),
                        "icon": template.get("icon"),
                        "color": template.get("color"),
                        "is_system": True,
                        "is_event": template.get("is_event", False),
                        "check_duplicates": template.get("check_duplicates", True),
                        "weight_coefficient": template.get("weight_coefficient", 1.0),
                        "is_context_anchor": template.get("is_context_anchor", False),
                        "is_voice_target": template.get("is_voice_target", False),
                        "extractable": template.get("extractable", True),
                    },
                )
                continue
            entity_type = EntityType(
                type_id=template["type_id"],
                company_id=company_id,
                namespace=init_namespace,
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
                created_at=datetime.now(UTC),
            )
            try:
                _ = await EntityType.create(entity_type)
                created_count += 1
            except UniqueViolationError:
                logger.info(
                    "crm.entitytype.worker.company.namespace",
                    type_id=template['type_id'],
                    company=company_id,
                    namespace=init_namespace,
                )

        return created_count

    async def _init_relationship_types(self, company_id: str, *, reseed: bool) -> int:
        """Создаёт или обновляет минимальное системное ядро связей.

        merge() внутри update уже обрабатывает INSERT-ON-CONFLICT для
        relationship_types (PK type_id + company_id), но check-then-update
        может увидеть None в обоих worker'ах. IntegrityError от merge ловится
        как успех (другой worker создал запись).
        """
        created_count = 0
        existing_relationship_types = await self._check_existing_relationship_types(company_id)
        existing_by_id = {item.type_id: item for item in existing_relationship_types}

        for template in SYSTEM_RELATIONSHIP_TYPE_TEMPLATES:
            existing = existing_by_id.get(template["type_id"])
            if existing is not None:
                if not reseed:
                    continue
                existing.name = template["name"]
                existing.description = template.get("description")
                # prompt — user-editable AI text; re-init не затирает правки компании.
                if existing.prompt is None:
                    existing.prompt = template.get("prompt")
                existing.is_directed = template.get("is_directed", True)
                existing.inverse_type_id = template.get("inverse_type_id")
                existing.icon = template.get("icon")
                existing.color = template.get("color")
                existing.is_system = True
                existing.weight_default = template.get("weight_default", 1.0)
                _ = await RelationshipType.update_loaded_by_company_and_type_id(existing)
                continue

            rel_type = RelationshipType(
                type_id=template["type_id"],
                company_id=company_id,
                name=template["name"],
                description=template.get("description"),
                prompt=template.get("prompt"),
                is_directed=template.get("is_directed", True),
                inverse_type_id=template.get("inverse_type_id"),
                icon=template.get("icon"),
                color=template.get("color"),
                is_system=True,
                weight_default=template.get("weight_default", 1.0),
                created_at=datetime.now(UTC),
            )
            try:
                _ = await RelationshipType.create(rel_type)
                created_count += 1
            except UniqueViolationError:
                logger.info(
                    "crm.relationshiptype.worker.company",
                    type_id=template["type_id"],
                    company_id=company_id,
                )

        return created_count

    async def _init_namespace_templates(self, company_id: str, *, reseed: bool) -> int:
        """Идемпотентно создаёт шаблоны namespace и их типы.

        check-then-create защищён от параллельных worker через IntegrityError при
        INSERT в NamespaceTemplate (unique: company_id, template_id).
        """
        created_count = 0
        for seed in NAMESPACE_TEMPLATE_SEEDS:
            raw_crm_settings = seed.get("crm_settings")
            seed_crm_settings = (
                require_json_object(raw_crm_settings, "namespace_template.crm_settings")
                if raw_crm_settings is not None
                else None
            )
            existing = await NamespaceTemplate.by_template_id(
                company_id, seed["template_id"]
            )
            if existing is not None:
                if not reseed:
                    continue
                existing.name = seed["name"]
                existing.description = seed.get("description")
                existing.icon = seed.get("icon")
                existing.is_system = True
                existing.crm_settings = seed_crm_settings
                existing.updated_at = datetime.now(UTC)
                existing = await existing.save(using="crm")
            else:
                try:
                    existing = await NamespaceTemplate.create(
                        NamespaceTemplate(
                            template_key=str(uuid.uuid4()),
                            company_id=company_id,
                            template_id=seed["template_id"],
                            name=seed["name"],
                            description=seed.get("description"),
                            icon=seed.get("icon"),
                            is_system=True,
                            crm_settings=seed_crm_settings,
                        )
                    )
                    created_count += 1
                except UniqueViolationError:
                    logger.info(
                        "crm.namespacetemplate.worker.company",
                        template_id=seed["template_id"],
                        company_id=company_id,
                    )
                    existing = await NamespaceTemplate.by_template_id(
                        company_id, seed["template_id"]
                    )
                    if existing is None:
                        raise RuntimeError(
                            f"NamespaceTemplate {seed['template_id']} not found after unique violation for company={company_id}"
                        )

            for item in seed["types"]:
                _ = await NamespaceTemplateType.upsert_by_template_key_and_type_id(
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

        if reseed:
            for retired_id in sorted(RETIRED_NAMESPACE_TEMPLATE_IDS):
                retired_row = await NamespaceTemplate.by_template_id(
                    company_id, retired_id
                )
                if retired_row is not None:
                    _ = await NamespaceTemplateType.delete_by_template_key(retired_row.template_key)
                    _ = await NamespaceTemplate.delete_by_id(retired_row.template_key)

        return created_count

    async def _check_existing_types(self, company_id: str) -> list[EntityType]:
        """
        Проверяет существующие типы для компании (прямой запрос к БД).

        Аргументы:
            company_id: ID компании

        Возвращает:
            Список существующих типов компании
        """
        return await EntityType.catalog(
            company_id=company_id,
        )

    async def _check_existing_relationship_types(self, company_id: str) -> list[RelationshipType]:
        return await RelationshipType.query_by_system_in_company(
            company_id,
            include_system=True,
        ).order_by("type_id").all()

    async def _ensure_company_entity(self, company_id: str, *, reseed: bool) -> str:
        """Идемпотентно создает CRM-сущность для компании-тенанта."""
        existing = await CRMEntity.list_by_entity_type_and_attribute(
            entity_type=COMPANY_ENTITY_TYPE,
            attribute_key=PLATFORM_COMPANY_ID_ATTR,
            attribute_value=company_id,
            company_id=company_id,
        )
        if existing:
            if reseed:
                await self._entity_access.sync_entity_created(existing[0])
            return existing[0].entity_id

        company = await Company.get(company_id)
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
        try:
            entity = await CRMEntity.create(entity)
            await index_crm_entity(self._rag, entity, replace=False)
        except UniqueViolationError:
            logger.info("crm.entity.worker.company", entity_id=entity.entity_id, company=company_id)
            raced = await CRMEntity.list_by_entity_type_and_attribute(
                entity_type=COMPANY_ENTITY_TYPE,
                attribute_key=PLATFORM_COMPANY_ID_ATTR,
                attribute_value=company_id,
                company_id=company_id,
            )
            if raced:
                await self._entity_access.sync_entity_created(raced[0])
                return raced[0].entity_id
            raise
        try:
            await self._entity_access.sync_entity_created(entity)
        except Exception:
            removed = await CRMEntity.delete_returning(entity.entity_id)
            if removed is not None:
                _ = await self._rag.delete_document(entity_namespace(removed), removed.entity_id)
            raise
        logger.info("crm.company_init.company_entity", entity_id=entity.entity_id, company_id=company_id)
        return entity.entity_id

    async def _ensure_default_namespace_record(self, company_id: str) -> None:
        """Запись Namespace в storage — отдельно от CRM graph entity namespace."""
        _ = company_id
        _ = await self._namespace_service.ensure_default()

    async def _ensure_personal_namespaces_for_members(self, company_id: str) -> int:
        """Идемпотентно создаёт personal namespace каждому member компании."""
        company = await Company.get(company_id)
        if company is None:
            raise ValueError(f"Company not found: {company_id}")
        ensured = 0
        for member_user_id in company.members:
            user = await User.get(member_user_id)
            if user is None:
                logger.warning(
                    "company_init.personal_ns_skip_missing_user",
                    company_id=company_id,
                    user_id=member_user_id,
                )
                continue
            await ensure_personal_namespace_for_user(
                self._namespace_service,
                user,
                company=company,
            )
            ensured += 1
        return ensured

    async def _ensure_namespace_entity(
        self,
        company_id: str,
        namespace_name: str,
        *,
        reseed: bool = False,
    ) -> str:
        """Идемпотентно создает CRM-сущность для namespace."""
        existing = await CRMEntity.list_by_entity_type_and_attribute(
            entity_type=NAMESPACE_ENTITY_TYPE,
            attribute_key=PLATFORM_NAMESPACE_ATTR,
            attribute_value=namespace_name,
            company_id=company_id,
        )
        if existing:
            if reseed:
                await self._entity_access.sync_entity_created(existing[0])
            return existing[0].entity_id

        company_entity_id = await self._ensure_company_entity(company_id, reseed=reseed)
        company = await Company.get(company_id)
        if company is None:
            raise ValueError(f"Company not found: {company_id}")

        entity = CRMEntity(
            entity_id=str(uuid.uuid4()),
            company_id=company_id,
            namespace=namespace_name,
            entity_type=NAMESPACE_ENTITY_TYPE,
            name=namespace_name,
            attributes={PLATFORM_NAMESPACE_ATTR: namespace_name},
            tags=[],
            user_id=company.owner_user_id or company_id,
        )
        try:
            entity = await CRMEntity.create(entity)
            await index_crm_entity(self._rag, entity, replace=False)
        except UniqueViolationError:
            logger.info("crm.namespace.entity.worker.company", entity_id=entity.entity_id, company=company_id)
            raced = await CRMEntity.list_by_entity_type_and_attribute(
                entity_type=NAMESPACE_ENTITY_TYPE,
                attribute_key=PLATFORM_NAMESPACE_ATTR,
                attribute_value=namespace_name,
                company_id=company_id,
            )
            if raced:
                await self._entity_access.sync_entity_created(raced[0])
                return raced[0].entity_id
            raise
        try:
            await self._entity_access.sync_entity_created(entity)
        except Exception:
            removed = await CRMEntity.delete_returning(entity.entity_id)
            if removed is not None:
                _ = await self._rag.delete_document(entity_namespace(removed), removed.entity_id)
            raise

        rel = Relationship(
            relationship_id=str(uuid.uuid4()),
            company_id=company_id,
            namespace=namespace_name,
            source_entity_id=entity.entity_id,
            target_entity_id=company_entity_id,
            relationship_type=BELONGS_TO_RELATIONSHIP_TYPE,
        )
        try:
            _ = await Relationship.create(rel)
        except UniqueViolationError:
            logger.info(
                "crm.relationship.worker.company",
                relationship_id=rel.relationship_id,
                company_id=company_id,
            )

        logger.info("crm.company_init.namespace_entity", entity_id=entity.entity_id, namespace=namespace_name)
        return entity.entity_id

    async def ensure_namespace_entity(self, company_id: str, namespace_name: str) -> str:
        return await self._ensure_namespace_entity(company_id, namespace_name, reseed=False)

    async def _ensure_default_organization_entity(self, company_id: str, *, reseed: bool) -> None:
        """Организация по умолчанию для графа CRM и company_mapping (is_owner)."""
        existing_mapping = await CompanyMapping.get(company_id)
        if existing_mapping is not None:
            return

        page = await CRMEntity.cursor_page(
            entity_type="organization",
            namespace="default",
            company_id=company_id,
            limit=1,
        )
        entities = page.items
        if len(entities) > 0:
            if reseed:
                await self._entity_access.sync_entity_created(entities[0])
            await CompanyMapping.ensure_for_company(company_id, entities[0].entity_id)
            return

        company = await Company.get(company_id)
        if company is None:
            raise ValueError(f"Company not found: {company_id}")

        entity = CRMEntity(
            entity_id=str(uuid.uuid4()),
            company_id=company_id,
            namespace="default",
            entity_type="organization",
            name=company.name,
            attributes={},
            tags=[],
            user_id=company.owner_user_id if company.owner_user_id else company_id,
        )
        try:
            entity = await CRMEntity.create(entity)
            await index_crm_entity(self._rag, entity, replace=False)
        except UniqueViolationError:
            logger.info("crm.organization.entity.worker.company", entity_id=entity.entity_id, company=company_id)
            page = await CRMEntity.cursor_page(
                entity_type="organization",
                namespace="default",
                company_id=company_id,
                limit=1,
            )
            entities = page.items
            if not entities:
                raise
            entity = entities[0]
            created_now = False
        else:
            created_now = True
        try:
            await self._entity_access.sync_entity_created(entity)
        except Exception:
            if created_now:
                removed = await CRMEntity.delete_returning(entity.entity_id)
                if removed is not None:
                    _ = await self._rag.delete_document(
                        entity_namespace(removed),
                        removed.entity_id,
                    )
            raise
        await CompanyMapping.ensure_for_company(company_id, entity.entity_id)
        logger.info(
            "crm.company.default_organization_created",
            entity_id=entity.entity_id,
            company_id=company_id,
        )


