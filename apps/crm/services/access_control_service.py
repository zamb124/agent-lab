"""
Сервис проверки доступа через AccessGrants.
"""

from datetime import UTC, date, datetime

from apps.crm.db.models import AccessGrant, CRMEntity
from apps.crm.db.repositories.access_grant_repository import AccessGrantRepository
from apps.crm.db.repositories.entity_type_repository import EntityTypeRepository
from core.context import get_context
from core.logging import get_logger
from core.types import JsonObject, require_json_object, require_json_value

logger = get_logger(__name__)


class AccessControlService:
    """Единая точка проверки доступа через AccessGrants"""

    def __init__(
        self,
        grant_repo: AccessGrantRepository,
        entity_type_repo: EntityTypeRepository,
    ) -> None:
        self._grant_repo: AccessGrantRepository = grant_repo
        self._entity_type_repo: EntityTypeRepository = entity_type_repo

    async def can_read_entity(
        self,
        entity: CRMEntity,
        user_id: str | None,
        company_id: str | None,
    ) -> bool:
        """Проверка доступа к entity"""

        # 1. Владелец всегда может
        if user_id and entity.user_id == user_id:
            return True

        # 2. Та же компания и явный рабочий namespace запроса (Context.active_namespace / заголовок).
        if user_id and company_id == entity.company_id:
            user_ns = await self._get_request_namespace()
            if user_ns is not None and user_ns == entity.namespace:
                return True

        # 3. AccessGrants для ENTITY (company_id ресурса — владелец гранта)
        entity_grants = await self._grant_repo.find_by_resource(
            resource_type="entity",
            resource_id=entity.entity_id,
            resource_company_id=entity.company_id,
        )

        for grant in entity_grants:
            if await self._check_grant(grant, user_id, company_id):
                return True

        # 4. AccessGrants для NAMESPACE
        namespace_grants = await self._grant_repo.find_by_resource(
            "namespace",
            entity.namespace,
            entity.company_id,
        )

        for grant in namespace_grants:
            if grant.grant_type == "public":
                continue
            if await self._check_grant(grant, user_id, company_id):
                return True

        return False

    async def can_write_entity(
        self,
        entity: CRMEntity,
        user_id: str,
        company_id: str,
    ) -> bool:
        """Проверка прав на редактирование"""

        # Владелец
        if entity.user_id == user_id:
            return True

        # Тот же namespace, что в контексте запроса (без подстановок).
        if company_id == entity.company_id:
            user_ns = await self._get_request_namespace()
            if user_ns is not None and user_ns == entity.namespace:
                return True

        # Grants с ролью editor/admin
        grants = await self._grant_repo.find_by_resource(
            "entity", entity.entity_id, entity.company_id
        )
        grants += await self._grant_repo.find_by_resource(
            "namespace", entity.namespace, entity.company_id
        )

        for grant in grants:
            if grant.role in ["editor", "admin"]:
                if await self._check_grant(grant, user_id, company_id):
                    return True

        return False

    async def filter_fields(
        self,
        entity: CRMEntity,
        user_id: str | None,
        company_id: str | None,
    ) -> CRMEntity | JsonObject:
        """Возвращает полную entity при полном доступе или dict с публичными полями."""

        # Проверяем ПОЛНЫЙ доступ (owner, same company+namespace, grants с ролью)
        has_full_access = await self._has_full_access(entity, user_id, company_id)
        if has_full_access:
            return entity

        # Проверяем публичные гранты
        entity_grants = await self._grant_repo.find_by_resource(
            "entity", entity.entity_id, entity.company_id
        )
        namespace_grants = await self._grant_repo.find_by_resource(
            "namespace", entity.namespace, entity.company_id
        )

        # Если есть хоть один public grant
        for grant in entity_grants + namespace_grants:
            if grant.grant_type == "public":
                # Expired?
                if grant.expires_at and grant.expires_at < datetime.now(UTC):
                    continue
                return await self._filter_public_fields(entity)

        raise PermissionError("Access denied")

    async def _filter_public_fields(
        self,
        entity: CRMEntity,
    ) -> JsonObject:
        """Фильтрация по EntityType.public_fields"""

        entity_type = await self._entity_type_repo.get_by_type_id(
            entity.entity_type,
            namespace=entity.namespace,
            company_id=entity.company_id,
        )

        # Возвращаем ТОЛЬКО публичные поля
        result: JsonObject = {
            "entity_id": entity.entity_id,
            "entity_type": entity.entity_type,
        }

        # Добавляем поля из public_fields
        if entity_type and entity_type.public_fields:
            for field_path in entity_type.public_fields:
                value = self._get_nested_value(entity, field_path)
                if value is not None:
                    self._set_nested_value(result, field_path, value)

        return result

    async def _has_full_access(
        self,
        entity: CRMEntity,
        user_id: str | None,
        company_id: str | None,
    ) -> bool:
        """Проверка ПОЛНОГО доступа (без учета публичных грантов)"""

        # Владелец
        if user_id and entity.user_id == user_id:
            return True

        if company_id and company_id == entity.company_id:
            user_ns = await self._get_request_namespace()
            if user_ns is not None and user_ns == entity.namespace:
                return True

        # Гранты с ролью (НЕ публичные)
        grants = await self._grant_repo.find_by_resource(
            "entity", entity.entity_id, entity.company_id
        )
        grants += await self._grant_repo.find_by_resource(
            "namespace", entity.namespace, entity.company_id
        )

        for grant in grants:
            # Пропускаем публичные гранты - они дают ограниченный доступ
            if grant.grant_type == "public":
                continue

            # User/Company гранты с ролью viewer+
            if grant.role in ["viewer", "editor", "admin"]:
                if await self._check_grant(grant, user_id, company_id):
                    return True

        return False

    async def _check_grant(
        self,
        grant: AccessGrant,
        user_id: str | None,
        company_id: str | None,
    ) -> bool:
        """Проверить конкретный grant"""

        # Expired?
        if grant.expires_at and grant.expires_at < datetime.now(UTC):
            return False

        # Public
        if grant.grant_type == "public":
            return True

        # User
        if grant.grant_type == "user" and user_id:
            return user_id == grant.target_user_id

        # Company
        if grant.grant_type == "company" and company_id:
            return company_id == grant.target_company_id

        return False

    def _get_nested_value(self, entity: CRMEntity, path: str) -> object | None:
        """Получить публично разрешенное значение по пути (например, attributes.position)."""
        keys = [key for key in path.split(".") if key]
        if not keys:
            return None
        if keys[0] == "attributes":
            if len(keys) == 1:
                return entity.attributes
            return self._get_json_path_value(entity.attributes, keys[1:])
        if len(keys) > 1:
            return None
        return self._get_entity_public_field(entity, keys[0])

    @staticmethod
    def _get_entity_public_field(entity: CRMEntity, field_name: str) -> object | None:
        if field_name == "entity_id":
            return entity.entity_id
        if field_name == "company_id":
            return entity.company_id
        if field_name == "namespace":
            return entity.namespace
        if field_name == "entity_type":
            return entity.entity_type
        if field_name == "entity_subtype":
            return entity.entity_subtype
        if field_name == "name":
            return entity.name
        if field_name == "description":
            return entity.description
        if field_name == "status":
            return entity.status
        if field_name == "tags":
            return entity.tags
        if field_name == "priority":
            return entity.priority
        if field_name == "due_date":
            return entity.due_date
        if field_name == "note_date":
            return entity.note_date
        if field_name == "assignees":
            return entity.assignees
        if field_name == "attachment_ids":
            return entity.attachment_ids
        if field_name == "user_id":
            return entity.user_id
        if field_name == "source_entity_id":
            return entity.source_entity_id
        if field_name == "source_company_id":
            return entity.source_company_id
        if field_name == "relevance":
            return entity.relevance
        if field_name == "created_at":
            return entity.created_at
        if field_name == "updated_at":
            return entity.updated_at
        return None

    @staticmethod
    def _get_json_path_value(obj: JsonObject, keys: list[str]) -> object | None:
        value: object = obj
        for key in keys:
            nested = AccessControlService._as_nested_json_object(value)
            if nested is None:
                return None
            value = nested.get(key)
        return value

    @staticmethod
    def _as_nested_json_object(value: object) -> JsonObject | None:
        try:
            return require_json_object(value, "nested access object")
        except ValueError:
            return None

    def _set_nested_value(self, obj: JsonObject, path: str, value: object) -> None:
        """Установить значение по пути"""
        keys = [key for key in path.split(".") if key]
        if not keys:
            return
        if isinstance(value, date | datetime):
            value = value.isoformat()
        json_value = require_json_value(value, f"public field {path}")
        for key in keys[:-1]:
            nested = self._as_nested_json_object(obj.get(key))
            if nested is None:
                nested = {}
                obj[key] = nested
            obj = nested
        obj[keys[-1]] = json_value

    async def batch_filter_readable(
        self,
        entities: list[CRMEntity],
        user_id: str | None,
        company_id: str | None,
        *,
        query_namespace: str | None = None,
    ) -> list[CRMEntity]:
        """
        Batch фильтрация сущностей по правам доступа с проставлением access_level.
        Один SQL-запрос для всех грантов вместо 2*N запросов.

        access_level = "owner" | "shared" | "public"
        """
        if not entities:
            return []

        user_ns = await self._get_request_namespace() if user_id else None
        now = datetime.now(UTC)

        needs_grant_check: list[CRMEntity] = []
        readable: list[CRMEntity] = []

        qns = (query_namespace or "").strip()
        for entity in entities:
            if user_id and entity.user_id == user_id:
                entity.access_level = "owner"
                readable.append(entity)
                continue
            if (
                user_id
                and company_id
                and qns
                and company_id == entity.company_id
                and entity.namespace == qns
            ):
                entity.access_level = "owner"
                readable.append(entity)
                continue
            if (
                user_id
                and company_id == entity.company_id
                and user_ns is not None
                and user_ns == entity.namespace
            ):
                entity.access_level = "owner"
                readable.append(entity)
                continue
            needs_grant_check.append(entity)

        if not needs_grant_check:
            return readable

        resource_keys: list[tuple[str, str]] = []
        for entity in needs_grant_check:
            resource_keys.append(("entity", entity.entity_id))
            resource_keys.append(("namespace", entity.namespace))

        unique_keys = list(set(resource_keys))
        grants_map = await self._grant_repo.find_by_resources_batch(unique_keys)

        for entity in needs_grant_check:
            entity_grants = grants_map.get(("entity", entity.entity_id), [])
            namespace_grants = grants_map.get(("namespace", entity.namespace), [])

            access_level = self._resolve_access_level(
                entity_grants,
                namespace_grants,
                user_id,
                company_id,
                now,
            )
            if access_level:
                entity.access_level = access_level
                readable.append(entity)

        return readable

    def _resolve_access_level(
        self,
        entity_grants: list[AccessGrant],
        namespace_grants: list[AccessGrant],
        user_id: str | None,
        company_id: str | None,
        now: datetime,
    ) -> str | None:
        """Определяет уровень доступа: shared > public > None."""
        for grant in entity_grants:
            if not self._check_grant_sync(grant, user_id, company_id, now):
                continue
            if grant.grant_type in ("user", "company"):
                return "shared"
            if grant.grant_type == "public":
                return "public"

        for grant in namespace_grants:
            if grant.grant_type == "public":
                continue
            if self._check_grant_sync(grant, user_id, company_id, now):
                return "shared"

        return None

    def _check_grant_sync(
        self,
        grant: AccessGrant,
        user_id: str | None,
        company_id: str | None,
        now: datetime,
    ) -> bool:
        """Синхронная проверка гранта (для batch-операций)."""
        if grant.expires_at and grant.expires_at < now:
            return False
        if grant.grant_type == "public":
            return True
        if grant.grant_type == "user" and user_id:
            return user_id == grant.target_user_id
        if grant.grant_type == "company" and company_id:
            return company_id == grant.target_company_id
        return False

    async def _get_request_namespace(self) -> str | None:
        """
        Namespace текущего запроса из Context (в т.ч. X-Platform-Namespace, воркер задаёт из задачи).

        Если в контексте не задано — None (не подставляем имена пространств).
        """
        ctx = get_context()
        if ctx is None:
            return None
        raw = (ctx.active_namespace or "").strip()
        if not raw:
            return None
        return raw
