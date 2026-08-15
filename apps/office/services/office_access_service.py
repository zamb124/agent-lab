"""Единая модель доступа Office: OpenFGA sole PDP + public link AuthN."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

from fastapi import Request

from apps.office.authz.tuples import (
    office_catalog_company_link,
    office_catalog_company_viewer_tuple,
    office_catalog_member_tuple,
    office_catalog_owner_tuple,
    office_catalog_parent_tuple,
    office_document_catalog_link,
    office_document_owner_tuple,
)
from apps.office.db.models import OfficeDocumentBinding, OfficeDocumentCatalog
from apps.office.db.repositories.access_repository import OfficeAccessRepository
from apps.office.db.repositories.catalog_repository import CatalogRepository
from apps.office.db.repositories.document_binding_repository import DocumentBindingRepository
from apps.office.models.api import (
    OfficeAccessMemberRelation,
    OfficePublicCatalogItem,
    OfficePublicCatalogItemsResponse,
    OfficePublicResolveResponse,
    OfficeResourceAccessMemberItem,
    OfficeResourceAccessPatchRequest,
    OfficeResourceAccessResponse,
    OfficeResourceAccessRotateLinkResponse,
)
from apps.office.services.public_link_tokens import create_share_token
from core.authz.models import AuthzCheckItem, AuthzObject, AuthzSubject, AuthzTuple
from core.authz.service import AuthzService
from core.authz.types import AuthzRelation, AuthzSubjectKind

OfficeLinkPermission = Literal["viewer", "editor"]
OfficeAccessResourceKind = Literal["catalog", "binding"]

_MEMBER_RELATIONS: tuple[AuthzRelation, ...] = (
    AuthzRelation.VIEWER,
    AuthzRelation.EDITOR,
)


@dataclass(frozen=True)
class PublicLinkTarget:
    kind: OfficeAccessResourceKind
    catalog: OfficeDocumentCatalog | None
    binding: OfficeDocumentBinding | None
    token_hash: str


class OfficeAccessService:
    def __init__(
        self,
        catalog_repository: CatalogRepository,
        document_binding_repository: DocumentBindingRepository,
        access_repository: OfficeAccessRepository,
        authz: AuthzService,
    ) -> None:
        self._catalog_repository: CatalogRepository = catalog_repository
        self._binding_repository: DocumentBindingRepository = document_binding_repository
        self._access_repository: OfficeAccessRepository = access_repository
        self._authz: AuthzService = authz

    @staticmethod
    def hash_link_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    @staticmethod
    def build_public_page_url(request: Request, raw_token: str) -> str:
        base = str(request.base_url).rstrip("/")
        return f"{base}/documents/p/{raw_token}"

    def _catalog_obj(self, catalog_id: str) -> AuthzObject:
        return AuthzObject.office_catalog(catalog_id)

    def _document_obj(self, file_id: str) -> AuthzObject:
        return AuthzObject.office_document(file_id)

    async def sync_catalog_created(
        self,
        catalog: OfficeDocumentCatalog,
        *,
        owner_user_id: str,
        company_visible: bool,
    ) -> None:
        writes: list[AuthzTuple] = [
            office_catalog_owner_tuple(catalog.catalog_id, owner_user_id),
            office_catalog_company_link(catalog.catalog_id, catalog.company_id),
        ]
        if catalog.parent_catalog_id is not None:
            writes.append(
                office_catalog_parent_tuple(catalog.catalog_id, catalog.parent_catalog_id)
            )
        if company_visible:
            writes.append(
                office_catalog_company_viewer_tuple(
                    catalog.catalog_id, catalog.company_id
                )
            )
        await self._authz.write(writes)

    async def sync_catalog_deleted(self, catalog_id: str) -> None:
        deletes = await self._authz.list_tuples(self._catalog_obj(catalog_id))
        if deletes:
            await self._authz.delete(deletes)

    async def sync_document_created(
        self,
        binding: OfficeDocumentBinding,
        *,
        owner_user_id: str,
    ) -> None:
        await self._authz.write(
            [
                office_document_owner_tuple(binding.file_id, owner_user_id),
                office_document_catalog_link(binding.file_id, binding.catalog_id),
            ]
        )

    async def sync_document_moved(
        self,
        binding: OfficeDocumentBinding,
        *,
        old_catalog_id: str,
    ) -> None:
        if old_catalog_id == binding.catalog_id:
            return
        await self._authz.write_and_delete(
            [office_document_catalog_link(binding.file_id, binding.catalog_id)],
            [office_document_catalog_link(binding.file_id, old_catalog_id)],
        )

    async def sync_document_deleted(self, file_id: str) -> None:
        deletes = await self._authz.list_tuples(self._document_obj(file_id))
        if deletes:
            await self._authz.delete(deletes)

    async def set_catalog_company_visible(
        self,
        catalog: OfficeDocumentCatalog,
        *,
        company_visible: bool,
    ) -> None:
        link = office_catalog_company_link(catalog.catalog_id, catalog.company_id)
        viewer = office_catalog_company_viewer_tuple(
            catalog.catalog_id, catalog.company_id
        )
        if company_visible:
            await self._authz.write([link, viewer])
        else:
            await self._authz.write_and_delete([link], [viewer])

    async def catalog_is_company_visible(self, catalog_id: str, company_id: str) -> bool:
        tuples = await self._authz.list_tuples(self._catalog_obj(catalog_id))
        company_members = AuthzSubject.company_member(company_id)
        return any(
            item.relation is AuthzRelation.VIEWER and item.subject == company_members
            for item in tuples
        )

    async def resolve_catalog_owner_user_id(self, catalog_id: str) -> str:
        subjects = await self._authz.list_users(
            self._catalog_obj(catalog_id),
            AuthzRelation.OWNER,
        )
        for subject in subjects:
            if subject.kind is AuthzSubjectKind.USER:
                return subject.value
        raise ValueError(f"office catalog {catalog_id} has no FGA owner")

    async def user_can_view_document(
        self,
        binding: OfficeDocumentBinding,
        *,
        company_id: str,
        namespace: str,
        user_id: str,
    ) -> bool:
        if binding.company_id != company_id or binding.namespace != namespace:
            return False
        if binding.deleted_at is not None:
            return False
        return await self._authz.can_view(self._document_obj(binding.file_id), user_id=user_id)

    async def user_can_manage_trashed_binding(
        self,
        binding: OfficeDocumentBinding,
        *,
        company_id: str,
        namespace: str,
        user_id: str,
    ) -> bool:
        if binding.company_id != company_id or binding.namespace != namespace:
            return False
        if binding.deleted_at is None:
            return False
        return await self._authz.can_view(self._document_obj(binding.file_id), user_id=user_id)

    async def list_accessible_catalogs_with_file_counts(
        self,
        *,
        company_id: str,
        namespace: str,
        user_id: str,
    ) -> list[tuple[OfficeDocumentCatalog, int]]:
        candidates = await self._catalog_repository.list_by_company_namespace(
            company_id=company_id,
            namespace=namespace,
        )
        if not candidates:
            return []
        checks = [
            AuthzCheckItem(
                subject=AuthzSubject.user(user_id),
                relation=AuthzRelation.CAN_VIEW,
                obj=self._catalog_obj(catalog.catalog_id),
                correlation_id=catalog.catalog_id,
            )
            for catalog in candidates
        ]
        allowed = await self._authz.batch_check(checks)
        result: list[tuple[OfficeDocumentCatalog, int]] = []
        for catalog, is_allowed in zip(candidates, allowed, strict=True):
            if not is_allowed:
                continue
            count = await self._catalog_repository.count_documents(catalog.catalog_id)
            result.append((catalog, count))
        return result

    async def binding_visible_in_public_catalog(
        self,
        binding: OfficeDocumentBinding,
    ) -> bool:
        if binding.deleted_at is not None:
            return False
        return binding.link_enabled

    async def resolve_public_token(self, raw_token: str) -> PublicLinkTarget:
        normalized = raw_token.strip()
        if normalized == "":
            raise ValueError("token обязателен")
        token_hash = self.hash_link_token(normalized)
        binding = await self._access_repository.get_binding_by_link_token_hash(token_hash)
        if binding is not None:
            return PublicLinkTarget(
                kind="binding",
                catalog=None,
                binding=binding,
                token_hash=token_hash,
            )
        catalog = await self._access_repository.get_catalog_by_link_token_hash(token_hash)
        if catalog is not None:
            return PublicLinkTarget(
                kind="catalog",
                catalog=catalog,
                binding=None,
                token_hash=token_hash,
            )
        raise ValueError("Ссылка не найдена")

    async def _list_member_items(self, obj: AuthzObject) -> list[OfficeResourceAccessMemberItem]:
        items: list[OfficeResourceAccessMemberItem] = []
        seen: set[tuple[str, str]] = set()
        for item in await self._authz.list_tuples(obj):
            if item.relation not in _MEMBER_RELATIONS:
                continue
            if item.subject.kind is not AuthzSubjectKind.USER:
                continue
            key = (item.subject.value, item.relation.value)
            if key in seen:
                continue
            seen.add(key)
            items.append(
                OfficeResourceAccessMemberItem(
                    user_id=item.subject.value,
                    relation=_relation_to_member(item.relation),
                )
            )
        items.sort(key=lambda row: (row.user_id, row.relation))
        return items

    async def get_catalog_access(
        self,
        catalog_id: str,
        company_id: str,
        namespace: str,
        _request: Request,
    ) -> OfficeResourceAccessResponse:
        catalog = await self._catalog_repository.get(catalog_id, company_id, namespace)
        if catalog is None:
            raise ValueError("Каталог не найден")
        members = await self._list_member_items(self._catalog_obj(catalog_id))
        return OfficeResourceAccessResponse(
            resource_kind="catalog",
            resource_id=catalog_id,
            company_visible=await self.catalog_is_company_visible(catalog_id, company_id),
            link_enabled=catalog.link_enabled,
            link_permission=_parse_link_permission(catalog.link_permission),
            public_url=None,
            members=members,
        )

    async def get_binding_access(
        self,
        binding: OfficeDocumentBinding,
        _request: Request,
    ) -> OfficeResourceAccessResponse:
        members = await self._list_member_items(self._document_obj(binding.file_id))
        company_visible = await self.catalog_is_company_visible(
            binding.catalog_id, binding.company_id
        )
        return OfficeResourceAccessResponse(
            resource_kind="binding",
            resource_id=binding.file_id,
            company_visible=company_visible,
            link_enabled=binding.link_enabled,
            link_permission=_parse_link_permission(binding.link_permission),
            public_url=None,
            members=members,
        )

    async def _replace_members(
        self,
        obj: AuthzObject,
        *,
        members: list[tuple[str, AuthzRelation]],
        owner_user_id: str | None,
    ) -> None:
        existing = await self._authz.list_tuples(obj)
        deletes = [
            item
            for item in existing
            if item.relation in _MEMBER_RELATIONS and item.subject.kind is AuthzSubjectKind.USER
        ]
        writes: list[AuthzTuple] = []
        for user_id, relation in members:
            if owner_user_id is not None and user_id == owner_user_id:
                continue
            writes.append(
                AuthzTuple(
                    subject=AuthzSubject.user(user_id),
                    relation=relation,
                    obj=obj,
                )
            )
        await self._authz.write_and_delete(writes, deletes)

    async def patch_catalog_access(
        self,
        catalog_id: str,
        company_id: str,
        namespace: str,
        body: OfficeResourceAccessPatchRequest,
        request: Request,
    ) -> tuple[OfficeResourceAccessResponse, str | None]:
        catalog = await self._catalog_repository.get(catalog_id, company_id, namespace)
        if catalog is None:
            raise ValueError("Каталог не найден")
        raw_token: str | None = None
        link_enabled = catalog.link_enabled
        link_token_hash = catalog.link_token_hash
        link_permission = catalog.link_permission
        if body.company_visible is not None:
            await self.set_catalog_company_visible(catalog, company_visible=body.company_visible)
            if body.company_visible and body.members:
                raise ValueError(
                    "Company-visible каталог доступен всей компании; members не задаются"
                )
        if body.link_enabled is not None:
            link_enabled = body.link_enabled
            if link_enabled:
                if link_token_hash is None:
                    raw_token, link_token_hash = create_share_token()
            else:
                link_token_hash = None
                raw_token = None
        if body.link_permission is not None:
            link_permission = body.link_permission
        updated_catalog = await self._access_repository.set_catalog_link(
            catalog_id,
            company_id,
            namespace,
            link_enabled=link_enabled,
            link_token_hash=link_token_hash,
            link_permission=link_permission,
        )
        if updated_catalog is None:
            raise ValueError("Каталог не найден")
        if body.members is not None:
            if await self.catalog_is_company_visible(catalog_id, company_id):
                if body.members:
                    raise ValueError(
                        "Company-visible каталог доступен всей компании в этом пространстве"
                    )
            else:
                owner_user_id = await self.resolve_catalog_owner_user_id(catalog_id)
                await self._replace_members(
                    self._catalog_obj(catalog_id),
                    members=[
                        (row.user_id, _member_to_relation(row.relation)) for row in body.members
                    ],
                    owner_user_id=owner_user_id,
                )
        response = await self.get_catalog_access(catalog_id, company_id, namespace, request)
        if raw_token is not None:
            response = response.model_copy(
                update={"public_url": self.build_public_page_url(request, raw_token)},
            )
        return response, raw_token

    async def patch_binding_access(
        self,
        binding: OfficeDocumentBinding,
        body: OfficeResourceAccessPatchRequest,
        request: Request,
    ) -> tuple[OfficeResourceAccessResponse, str | None]:
        raw_token: str | None = None
        link_enabled = binding.link_enabled
        link_token_hash = binding.link_token_hash
        link_permission = binding.link_permission
        if body.company_visible is not None:
            raise ValueError("company_visible задаётся на каталоге, не на документе")
        if body.link_enabled is not None:
            link_enabled = body.link_enabled
            if link_enabled:
                if link_token_hash is None:
                    raw_token, link_token_hash = create_share_token()
            else:
                link_token_hash = None
        if body.link_permission is not None:
            link_permission = body.link_permission
        updated_binding = await self._access_repository.set_document_link(
            binding.file_id,
            link_enabled=link_enabled,
            link_token_hash=link_token_hash,
            link_permission=link_permission,
        )
        if updated_binding is None:
            raise ValueError("Привязка не найдена")
        if body.members is not None:
            await self._replace_members(
                self._document_obj(binding.file_id),
                members=[(row.user_id, _member_to_relation(row.relation)) for row in body.members],
                owner_user_id=binding.created_by_user_id,
            )
        response = await self.get_binding_access(updated_binding, request)
        if raw_token is not None:
            response = response.model_copy(
                update={"public_url": self.build_public_page_url(request, raw_token)},
            )
        return response, raw_token

    async def add_catalog_member(
        self,
        catalog_id: str,
        company_id: str,
        namespace: str,
        *,
        user_id: str,
        relation: AuthzRelation = AuthzRelation.VIEWER,
    ) -> None:
        catalog = await self._catalog_repository.get(catalog_id, company_id, namespace)
        if catalog is None:
            raise ValueError("Каталог не найден")
        if await self.catalog_is_company_visible(catalog_id, company_id):
            raise ValueError("Company-visible каталог доступен всей компании в этом пространстве")
        owner_user_id = await self.resolve_catalog_owner_user_id(catalog_id)
        if user_id == owner_user_id:
            raise ValueError("Владелец уже имеет полный доступ к каталогу")
        await self._authz.write([office_catalog_member_tuple(catalog_id, user_id, relation)])

    async def remove_catalog_member(self, catalog_id: str, user_id: str) -> None:
        owner_user_id = await self.resolve_catalog_owner_user_id(catalog_id)
        if user_id == owner_user_id:
            raise ValueError("Нельзя удалить владельца из members")
        await self._authz.delete(
            [
                office_catalog_member_tuple(catalog_id, user_id, AuthzRelation.VIEWER),
                office_catalog_member_tuple(catalog_id, user_id, AuthzRelation.EDITOR),
            ]
        )

    async def list_catalog_member_user_ids(self, catalog_id: str) -> list[str]:
        items = await self._list_member_items(self._catalog_obj(catalog_id))
        return sorted({item.user_id for item in items})

    async def rotate_catalog_link(
        self,
        catalog_id: str,
        company_id: str,
        namespace: str,
        request: Request,
    ) -> OfficeResourceAccessRotateLinkResponse:
        catalog = await self._catalog_repository.get(catalog_id, company_id, namespace)
        if catalog is None:
            raise ValueError("Каталог не найден")
        if not catalog.link_enabled:
            raise ValueError("Публичная ссылка не включена")
        raw_token, token_hash = create_share_token()
        updated = await self._access_repository.set_catalog_link(
            catalog_id,
            company_id,
            namespace,
            link_enabled=True,
            link_token_hash=token_hash,
            link_permission=catalog.link_permission,
        )
        if updated is None:
            raise ValueError("Каталог не найден")
        return OfficeResourceAccessRotateLinkResponse(
            public_url=self.build_public_page_url(request, raw_token),
        )

    async def rotate_binding_link(
        self,
        binding: OfficeDocumentBinding,
        request: Request,
    ) -> OfficeResourceAccessRotateLinkResponse:
        if not binding.link_enabled:
            raise ValueError("Публичная ссылка не включена")
        raw_token, token_hash = create_share_token()
        updated = await self._access_repository.set_document_link(
            binding.file_id,
            link_enabled=True,
            link_token_hash=token_hash,
            link_permission=binding.link_permission,
        )
        if updated is None:
            raise ValueError("Привязка не найдена")
        return OfficeResourceAccessRotateLinkResponse(
            public_url=self.build_public_page_url(request, raw_token),
        )

    async def build_public_resolve(self, target: PublicLinkTarget) -> OfficePublicResolveResponse:
        if target.kind == "binding":
            binding = target.binding
            if binding is None:
                raise ValueError("binding обязателен")
            return OfficePublicResolveResponse(
                resource_kind="binding",
                resource_id=binding.file_id,
                title=binding.title,
                link_permission=_parse_link_permission(binding.link_permission),
                file_id=binding.file_id,
                catalog_id=binding.catalog_id,
            )
        catalog = target.catalog
        if catalog is None:
            raise ValueError("catalog обязателен")
        return OfficePublicResolveResponse(
            resource_kind="catalog",
            resource_id=catalog.catalog_id,
            title=catalog.title,
            link_permission=_parse_link_permission(catalog.link_permission),
            file_id=None,
            catalog_id=catalog.catalog_id,
        )

    async def list_public_catalog_items(
        self, target: PublicLinkTarget
    ) -> OfficePublicCatalogItemsResponse:
        if target.kind != "catalog" or target.catalog is None:
            raise ValueError("Токен не относится к каталогу")
        catalog = target.catalog
        bindings = await self._binding_repository.list_by_company_namespace_and_catalog(
            catalog.company_id,
            catalog.namespace,
            catalog.catalog_id,
        )
        items: list[OfficePublicCatalogItem] = []
        for binding in bindings:
            if not await self.binding_visible_in_public_catalog(binding):
                continue
            items.append(
                OfficePublicCatalogItem(
                    title=binding.title,
                    file_id=binding.file_id,
                    file_category=binding.file_category,
                    onlyoffice_document_type=binding.onlyoffice_document_type,
                    link_permission=_parse_link_permission(binding.link_permission),
                )
            )
        return OfficePublicCatalogItemsResponse(
            catalog_id=catalog.catalog_id,
            title=catalog.title,
            items=items,
        )

    async def resolve_public_catalog_binding_open(
        self,
        catalog_target: PublicLinkTarget,
        file_id: str,
    ) -> OfficeDocumentBinding:
        if catalog_target.kind != "catalog" or catalog_target.catalog is None:
            raise ValueError("Токен не относится к каталогу")
        catalog = catalog_target.catalog
        binding = await self._binding_repository.get(
            file_id,
            catalog.company_id,
            catalog.namespace,
        )
        if binding is None or binding.deleted_at is not None:
            raise ValueError("Файл не найден")
        if binding.catalog_id != catalog.catalog_id:
            raise ValueError("Файл не принадлежит каталогу")
        if not await self.binding_visible_in_public_catalog(binding):
            raise ValueError("Файл недоступен по публичной ссылке")
        return binding


def _parse_link_permission(value: str) -> OfficeLinkPermission:
    if value == "editor":
        return "editor"
    if value == "viewer":
        return "viewer"
    raise ValueError(f"Неизвестное link_permission: {value}")


def _member_to_relation(value: OfficeAccessMemberRelation) -> AuthzRelation:
    mapping: dict[OfficeAccessMemberRelation, AuthzRelation] = {
        "viewer": AuthzRelation.VIEWER,
        "editor": AuthzRelation.EDITOR,
    }
    return mapping[value]


def _relation_to_member(relation: AuthzRelation) -> OfficeAccessMemberRelation:
    if relation is AuthzRelation.VIEWER:
        return "viewer"
    if relation is AuthzRelation.EDITOR:
        return "editor"
    raise ValueError(f"unsupported AuthzRelation for member: {relation}")
