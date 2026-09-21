"""CRM grants: единственный store — OpenFGA tuples."""

from __future__ import annotations

import base64
from typing import Literal

from apps.crm.authz.tuples import crm_grant_tuple
from apps.crm.db.repositories.entity_repository import EntityRepository
from apps.crm.models.grant_models import (
    AccessGrantResponse,
    GrantResourceType,
    GrantRole,
    GrantSubjectKind,
)
from core.authz.errors import AuthzDenied
from core.authz.ids import parse_namespace_key
from core.authz.models import AuthzObject, AuthzSubject, AuthzTuple
from core.authz.service import AuthzService
from core.authz.types import AuthzObjectType, AuthzRelation, AuthzSubjectKind
from core.logging import get_logger

logger = get_logger(__name__)

_GRANT_LIST_RELATIONS: frozenset[AuthzRelation] = frozenset(
    {
        AuthzRelation.OWNER,
        AuthzRelation.ADMIN,
        AuthzRelation.EDITOR,
        AuthzRelation.VIEWER,
    }
)

_GRANT_SUBJECT_KINDS: frozenset[AuthzSubjectKind] = frozenset(
    {
        AuthzSubjectKind.USER,
        AuthzSubjectKind.PUBLIC,
        AuthzSubjectKind.COMPANY_MEMBER,
    }
)


def encode_grant_id(obj: AuthzObject, relation: AuthzRelation, subject: AuthzSubject) -> str:
    raw = f"{obj.fga_id}|{relation.value}|{subject.fga_user}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def decode_grant_id(grant_id: str) -> tuple[AuthzObject, AuthzRelation, AuthzSubject]:
    padding = "=" * (-len(grant_id) % 4)
    decoded = base64.urlsafe_b64decode(grant_id + padding).decode("utf-8")
    parts = decoded.split("|", 2)
    if len(parts) != 3:
        raise ValueError("invalid grant_id")
    fga_id, relation_raw, subject_raw = parts
    obj = AuthzObject.from_fga_id(fga_id)
    relation = AuthzRelation(relation_raw)
    if subject_raw == "user:*":
        subject = AuthzSubject.public()
    elif subject_raw.startswith("user:"):
        subject = AuthzSubject.user(subject_raw.removeprefix("user:"))
    elif subject_raw.startswith("company:") and subject_raw.endswith("#member"):
        company_id = subject_raw.removeprefix("company:").removesuffix("#member")
        subject = AuthzSubject.company_member(company_id)
    else:
        raise ValueError(f"unsupported grant subject: {subject_raw}")
    return obj, relation, subject


def _as_grant_role(relation: AuthzRelation) -> GrantRole:
    if relation is AuthzRelation.OWNER:
        return "owner"
    if relation is AuthzRelation.ADMIN:
        return "admin"
    if relation is AuthzRelation.EDITOR:
        return "editor"
    if relation is AuthzRelation.VIEWER:
        return "viewer"
    raise ValueError(f"unsupported grant relation: {relation.value}")


def _response_from_tuple(
    *,
    obj: AuthzObject,
    relation: AuthzRelation,
    subject: AuthzSubject,
    resource_company_id: str | None,
) -> AccessGrantResponse:
    resource_type: Literal["entity", "namespace"]
    if obj.object_type is AuthzObjectType.CRM_ENTITY:
        resource_type = "entity"
        resource_id = obj.object_key
    elif obj.object_type is AuthzObjectType.CRM_NAMESPACE:
        resource_type = "namespace"
        company_part, resource_id = parse_namespace_key(obj.object_key)
        resource_company_id = company_part
    else:
        raise ValueError(f"unsupported grant object type: {obj.object_type}")

    grant_type: GrantSubjectKind
    if subject.kind is AuthzSubjectKind.PUBLIC:
        grant_type = "public"
        target_user_id = None
        target_company_id = None
    elif subject.kind is AuthzSubjectKind.USER:
        grant_type = "user"
        target_user_id = subject.value
        target_company_id = None
    elif subject.kind is AuthzSubjectKind.COMPANY_MEMBER:
        grant_type = "company"
        target_user_id = None
        target_company_id = subject.value
    else:
        raise ValueError(f"unsupported grant subject kind: {subject.kind}")

    return AccessGrantResponse(
        grant_id=encode_grant_id(obj, relation, subject),
        resource_type=resource_type,
        resource_id=resource_id,
        resource_company_id=resource_company_id,
        grant_type=grant_type,
        target_user_id=target_user_id,
        target_company_id=target_company_id,
        role=_as_grant_role(relation),
    )


class AccessGrantService:
    """Гранты CRM: write/list/revoke только OpenFGA."""

    def __init__(
        self,
        entity_repo: EntityRepository,
        authz: AuthzService,
    ) -> None:
        self._entity_repo: EntityRepository = entity_repo
        self._authz: AuthzService = authz

    async def _require_entity_share(self, entity_id: str, user_id: str) -> None:
        await self._authz.require_relation(
            AuthzRelation.CAN_SHARE,
            AuthzObject.crm_entity(entity_id),
            user_id=user_id,
        )

    async def _require_namespace_share(
        self, company_id: str, namespace: str, user_id: str
    ) -> None:
        await self._authz.require_relation(
            AuthzRelation.CAN_SHARE,
            AuthzObject.crm_namespace(company_id, namespace),
            user_id=user_id,
        )

    async def grant_entity_public(
        self, entity_id: str, created_by: str
    ) -> AccessGrantResponse:
        entity = await self._entity_repo.get(entity_id)
        if not entity:
            raise ValueError("Entity not found")
        await self._require_entity_share(entity_id, created_by)
        tuple_item = crm_grant_tuple(
            resource_type="entity",
            resource_id=entity_id,
            resource_company_id=entity.company_id,
            grant_type="public",
            role="viewer",
            target_user_id=None,
            target_company_id=None,
        )
        await self._authz.write([tuple_item])
        logger.info("crm.entity.made.public", entity_id=entity_id, created_by=created_by)
        return _response_from_tuple(
            obj=tuple_item.obj,
            relation=tuple_item.relation,
            subject=tuple_item.subject,
            resource_company_id=entity.company_id,
        )

    async def grant_entity_to_user(
        self,
        entity_id: str,
        target_user_id: str,
        role: str,
        created_by: str,
    ) -> AccessGrantResponse:
        entity = await self._entity_repo.get(entity_id)
        if not entity:
            raise ValueError("Entity not found")
        await self._require_entity_share(entity_id, created_by)
        tuple_item = crm_grant_tuple(
            resource_type="entity",
            resource_id=entity_id,
            resource_company_id=entity.company_id,
            grant_type="user",
            role=role,
            target_user_id=target_user_id,
            target_company_id=None,
        )
        await self._authz.write([tuple_item])
        logger.info(
            "crm.entity.shared.user.role",
            entity_id=entity_id,
            target_user_id=target_user_id,
            role=role,
        )
        return _response_from_tuple(
            obj=tuple_item.obj,
            relation=tuple_item.relation,
            subject=tuple_item.subject,
            resource_company_id=entity.company_id,
        )

    async def grant_entity_to_company(
        self,
        entity_id: str,
        target_company_id: str,
        role: str,
        created_by: str,
    ) -> AccessGrantResponse:
        entity = await self._entity_repo.get(entity_id)
        if not entity:
            raise ValueError("Entity not found")
        await self._require_entity_share(entity_id, created_by)
        tuple_item = crm_grant_tuple(
            resource_type="entity",
            resource_id=entity_id,
            resource_company_id=entity.company_id,
            grant_type="company",
            role=role,
            target_user_id=None,
            target_company_id=target_company_id,
        )
        await self._authz.write([tuple_item])
        logger.info(
            "crm.entity.shared.company.role",
            entity_id=entity_id,
            target_company_id=target_company_id,
            role=role,
        )
        return _response_from_tuple(
            obj=tuple_item.obj,
            relation=tuple_item.relation,
            subject=tuple_item.subject,
            resource_company_id=entity.company_id,
        )

    async def grant_namespace_public(
        self,
        namespace: str,
        company_id: str,
        created_by: str,
    ) -> AccessGrantResponse:
        _ = (namespace, company_id, created_by)
        raise ValueError(
            "namespace public ACL is forbidden: use entity public (user:*) instead"
        )

    async def grant_namespace_to_user(
        self,
        namespace: str,
        company_id: str,
        target_user_id: str,
        role: str,
        created_by: str,
    ) -> AccessGrantResponse:
        await self._require_namespace_share(company_id, namespace, created_by)
        tuple_item = crm_grant_tuple(
            resource_type="namespace",
            resource_id=namespace,
            resource_company_id=company_id,
            grant_type="user",
            role=role,
            target_user_id=target_user_id,
            target_company_id=None,
        )
        await self._authz.write([tuple_item])
        logger.info(
            "crm.namespace.shared.user.role",
            namespace=namespace,
            target_user_id=target_user_id,
            role=role,
        )
        return _response_from_tuple(
            obj=tuple_item.obj,
            relation=tuple_item.relation,
            subject=tuple_item.subject,
            resource_company_id=company_id,
        )

    async def grant_namespace_to_company(
        self,
        namespace: str,
        company_id: str,
        target_company_id: str,
        role: str,
        created_by: str,
    ) -> AccessGrantResponse:
        await self._require_namespace_share(company_id, namespace, created_by)
        tuple_item = crm_grant_tuple(
            resource_type="namespace",
            resource_id=namespace,
            resource_company_id=company_id,
            grant_type="company",
            role=role,
            target_user_id=None,
            target_company_id=target_company_id,
        )
        await self._authz.write([tuple_item])
        logger.info(
            "crm.namespace.shared.company.role",
            namespace=namespace,
            target_company_id=target_company_id,
            role=role,
        )
        return _response_from_tuple(
            obj=tuple_item.obj,
            relation=tuple_item.relation,
            subject=tuple_item.subject,
            resource_company_id=company_id,
        )

    async def revoke_grant(self, grant_id: str, user_id: str) -> None:
        obj, relation, subject = decode_grant_id(grant_id)
        if obj.object_type is AuthzObjectType.CRM_ENTITY:
            await self._require_entity_share(obj.object_key, user_id)
        elif obj.object_type is AuthzObjectType.CRM_NAMESPACE:
            company_id, namespace = parse_namespace_key(obj.object_key)
            await self._require_namespace_share(company_id, namespace, user_id)
        else:
            raise ValueError("unsupported grant object")
        await self._authz.delete(
            [AuthzTuple(subject=subject, relation=relation, obj=obj)]
        )
        logger.info("crm.grant.revoked", grant_id=grant_id, user_id=user_id)

    async def list_grants(
        self,
        resource_type: GrantResourceType,
        resource_id: str,
        resource_company_id: str | None = None,
    ) -> list[AccessGrantResponse]:
        if resource_type == "entity":
            obj = AuthzObject.crm_entity(resource_id)
            company_id = resource_company_id
            if company_id is None:
                entity = await self._entity_repo.get(resource_id)
                if entity is None:
                    raise ValueError("Entity not found")
                company_id = entity.company_id
        else:
            if not resource_company_id:
                raise ValueError("resource_company_id is required for namespace grants")
            obj = AuthzObject.crm_namespace(resource_company_id, resource_id)
            company_id = resource_company_id

        tuples = await self._authz.list_tuples(obj)
        items: list[AccessGrantResponse] = []
        seen: set[str] = set()
        for item in tuples:
            if item.relation not in _GRANT_LIST_RELATIONS:
                continue
            if item.subject.kind not in _GRANT_SUBJECT_KINDS:
                continue
            response = _response_from_tuple(
                obj=obj,
                relation=item.relation,
                subject=item.subject,
                resource_company_id=company_id,
            )
            if response.grant_id in seen:
                continue
            seen.add(response.grant_id)
            items.append(response)
        return items

    async def get_grant(self, grant_id: str) -> AccessGrantResponse:
        obj, relation, subject = decode_grant_id(grant_id)
        tuples = await self._authz.list_tuples(obj, relation=relation)
        matched = False
        for item in tuples:
            if item.subject.fga_user == subject.fga_user:
                matched = True
                break
        if not matched:
            raise ValueError("Grant not found")
        company_id: str | None = None
        if obj.object_type is AuthzObjectType.CRM_NAMESPACE:
            company_id, _namespace = parse_namespace_key(obj.object_key)
        elif obj.object_type is AuthzObjectType.CRM_ENTITY:
            entity = await self._entity_repo.get(obj.object_key)
            if entity is not None:
                company_id = entity.company_id
        return _response_from_tuple(
            obj=obj,
            relation=relation,
            subject=subject,
            resource_company_id=company_id,
        )


# Re-export for callers that catch AuthzDenied from share gates
__all__ = [
    "AccessGrantService",
    "AuthzDenied",
    "decode_grant_id",
    "encode_grant_id",
]
