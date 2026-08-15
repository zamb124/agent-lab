"""CRM entity access: OpenFGA tuple sync + field extras."""

from __future__ import annotations

from datetime import date, datetime

from apps.crm.authz.tuples import (
    crm_entity_namespace_link,
    crm_entity_owner_tuple,
    crm_namespace_company_editor_tuple,
    crm_namespace_company_link,
    crm_namespace_company_viewer_tuple,
)
from apps.crm.db.models import CRMEntity
from apps.crm.db.repositories.entity_type_repository import EntityTypeRepository
from core.authz.errors import AuthzDenied
from core.authz.models import AuthzCheckItem, AuthzObject, AuthzSubject, AuthzTuple
from core.authz.service import AuthzService
from core.authz.types import AuthzRelation, AuthzSubjectKind
from core.logging import get_logger
from core.types import JsonObject, require_json_object, require_json_value

logger = get_logger(__name__)

_GRANT_RELATIONS: tuple[AuthzRelation, ...] = (
    AuthzRelation.OWNER,
    AuthzRelation.ADMIN,
    AuthzRelation.EDITOR,
    AuthzRelation.VIEWER,
)


class CrmEntityAccessService:
    """CRM entity ACL: FGA checks, tuple sync, public field projection."""

    def __init__(
        self,
        entity_type_repo: EntityTypeRepository,
        authz: AuthzService,
    ) -> None:
        self._entity_type_repo: EntityTypeRepository = entity_type_repo
        self._authz: AuthzService = authz

    async def sync_entity_created(self, entity: CRMEntity) -> None:
        """Пишет owner + namespace TTU links в OpenFGA (fail-closed)."""
        if not entity.user_id:
            raise ValueError("sync_entity_created: entity.user_id is required")
        await self._authz.write(
            [
                crm_namespace_company_link(entity.company_id, entity.namespace),
                crm_namespace_company_viewer_tuple(
                    entity.company_id, entity.namespace
                ),
                crm_namespace_company_editor_tuple(
                    entity.company_id, entity.namespace
                ),
                crm_entity_owner_tuple(entity.entity_id, entity.user_id),
                crm_entity_namespace_link(
                    entity.entity_id, entity.company_id, entity.namespace
                ),
            ]
        )

    async def _entity_grant_tuples(self, entity_id: str) -> list[AuthzTuple]:
        obj = AuthzObject.crm_entity(entity_id)
        tuples = await self._authz.list_tuples(obj)
        return [
            item
            for item in tuples
            if item.relation in _GRANT_RELATIONS
            or item.relation is AuthzRelation.NAMESPACE
        ]

    async def sync_entity_deleted(self, entity: CRMEntity) -> None:
        """Удаляет OpenFGA tuples сущности (owner/namespace/grants)."""
        deletes = await self._entity_grant_tuples(entity.entity_id)
        if deletes:
            await self._authz.delete(deletes)

    async def sync_entity_merged(
        self,
        *,
        source: CRMEntity,
        survivor: CRMEntity,
    ) -> None:
        """Снимает FGA с source; переносит share-tuples на survivor; пишет links survivor."""
        source_obj = AuthzObject.crm_entity(source.entity_id)
        source_tuples = await self._authz.list_tuples(source_obj)
        deletes = list(source_tuples)

        writes: list[AuthzTuple] = [
            crm_namespace_company_link(survivor.company_id, survivor.namespace),
            crm_namespace_company_viewer_tuple(
                survivor.company_id, survivor.namespace
            ),
            crm_namespace_company_editor_tuple(
                survivor.company_id, survivor.namespace
            ),
            crm_entity_namespace_link(
                survivor.entity_id, survivor.company_id, survivor.namespace
            ),
        ]
        if survivor.user_id:
            writes.append(
                crm_entity_owner_tuple(survivor.entity_id, survivor.user_id)
            )

        survivor_obj = AuthzObject.crm_entity(survivor.entity_id)
        for item in source_tuples:
            if item.relation is AuthzRelation.NAMESPACE:
                continue
            if item.relation is AuthzRelation.OWNER:
                continue
            if item.relation not in (
                AuthzRelation.VIEWER,
                AuthzRelation.EDITOR,
                AuthzRelation.ADMIN,
            ):
                continue
            if item.subject.kind is AuthzSubjectKind.OBJECT:
                continue
            writes.append(
                AuthzTuple(
                    subject=item.subject,
                    relation=item.relation,
                    obj=survivor_obj,
                )
            )

        await self._authz.write_and_delete(writes, deletes)

    def _subject(self, user_id: str | None) -> AuthzSubject:
        if user_id:
            return AuthzSubject.user(user_id)
        return AuthzSubject.public()

    async def _direct_grant_tuples(self, obj: AuthzObject) -> list[AuthzTuple]:
        """Прямые owner/admin/editor/viewer tuples (без TTU / company#member expand)."""
        tuples = await self._authz.list_tuples(obj)
        return [item for item in tuples if item.relation in _GRANT_RELATIONS]

    async def _user_has_non_public_view_path(
        self, obj: AuthzObject, user_id: str
    ) -> bool:
        """True если на объекте есть прямой user-tuple (не user:*)."""
        for item in await self._direct_grant_tuples(obj):
            if item.subject.kind is AuthzSubjectKind.USER and item.subject.value == user_id:
                return True
        return False

    async def _has_public_viewer(self, obj: AuthzObject) -> bool:
        tuples = await self._authz.list_tuples(obj, relation=AuthzRelation.VIEWER)
        return any(item.subject.kind is AuthzSubjectKind.PUBLIC for item in tuples)

    async def filter_fields(
        self,
        entity: CRMEntity,
        user_id: str | None,
        company_id: str | None,
    ) -> CRMEntity | JsonObject:
        """Полная entity при can_edit / non-public view; public projection при только user:*."""
        _ = company_id
        obj = AuthzObject.crm_entity(entity.entity_id)

        can_edit = False
        if user_id:
            can_edit = await self._authz.can_edit(obj, user_id=user_id)
        if can_edit:
            return entity

        can_view = await self._authz.can_view(obj, user_id=user_id)
        if not can_view:
            raise AuthzDenied(f"denied view crm_entity:{entity.entity_id}")

        has_public = await self._has_public_viewer(obj)
        if not has_public:
            return entity

        if user_id and await self._user_has_non_public_view_path(obj, user_id):
            return entity

        return await self._filter_public_fields(entity)

    async def _filter_public_fields(self, entity: CRMEntity) -> JsonObject:
        entity_type = await self._entity_type_repo.get_by_type_id(
            entity.entity_type,
            namespace=entity.namespace,
            company_id=entity.company_id,
        )
        result: JsonObject = {
            "entity_id": entity.entity_id,
            "entity_type": entity.entity_type,
        }
        if entity_type and entity_type.public_fields:
            for field_path in entity_type.public_fields:
                value = self._get_nested_value(entity, field_path)
                if value is not None:
                    self._set_nested_value(result, field_path, value)
        return result

    def _get_nested_value(self, entity: CRMEntity, path: str) -> object | None:
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
        mapping: dict[str, object | None] = {
            "entity_id": entity.entity_id,
            "company_id": entity.company_id,
            "namespace": entity.namespace,
            "entity_type": entity.entity_type,
            "entity_subtype": entity.entity_subtype,
            "name": entity.name,
            "description": entity.description,
            "status": entity.status,
            "tags": entity.tags,
            "note_date": entity.note_date,
            "attachment_ids": entity.attachment_ids,
            "user_id": entity.user_id,
            "source_entity_id": entity.source_entity_id,
            "source_company_id": entity.source_company_id,
            "relevance": entity.relevance,
            "created_at": entity.created_at,
            "updated_at": entity.updated_at,
        }
        return mapping.get(field_name)

    @staticmethod
    def _get_json_path_value(obj: JsonObject, keys: list[str]) -> object | None:
        value: object = obj
        for key in keys:
            nested = CrmEntityAccessService._as_nested_json_object(value)
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
        """Пакетный CAN_VIEW через OpenFGA Check; access_level — CAN_ADMIN (owner) иначе shared.

        Public projection считается в ``filter_fields`` (GET), не через ``list_users``:
        ``crm_entity.viewer`` включает ``company#member`` и ListUsers разворачивает roster.
        """
        _ = company_id
        _ = query_namespace
        if not entities:
            return []

        subject = self._subject(user_id)
        checks = [
            AuthzCheckItem(
                subject=subject,
                relation=AuthzRelation.CAN_VIEW,
                obj=AuthzObject.crm_entity(entity.entity_id),
                correlation_id=entity.entity_id,
            )
            for entity in entities
        ]
        allowed = await self._authz.batch_check(checks)
        readable_entities = [
            entity for entity, ok in zip(entities, allowed, strict=True) if ok
        ]
        if not readable_entities:
            return []
        if user_id is None:
            for entity in readable_entities:
                entity.access_level = "public"
            return readable_entities

        admin_allowed = await self._authz.batch_check(
            [
                AuthzCheckItem(
                    subject=subject,
                    relation=AuthzRelation.CAN_ADMIN,
                    obj=AuthzObject.crm_entity(entity.entity_id),
                    correlation_id=entity.entity_id,
                )
                for entity in readable_entities
            ]
        )
        for entity, is_admin in zip(readable_entities, admin_allowed, strict=True):
            entity.access_level = "owner" if is_admin else "shared"
        return readable_entities
