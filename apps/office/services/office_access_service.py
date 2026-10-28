"""Единая модель доступа Office: OpenFGA sole PDP + public link AuthN."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

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
from apps.office.models.link import DocumentLink
from apps.office.services.document_lifecycle import document_title
from apps.office.services.file_binding_metadata import resolve_binding_metadata
from apps.office.services.public_link_tokens import create_share_token
from core.auth.utils import hash_token
from core.authz.models import AuthzCheckItem, AuthzObject, AuthzSubject, AuthzTuple
from core.authz.service import AuthzService
from core.authz.types import AuthzRelation, AuthzSubjectKind
from core.documents.authz.tuples import (
    document_catalog_company_link,
    document_catalog_company_viewer_tuple,
    document_catalog_member_tuple,
    document_catalog_owner_tuple,
    document_catalog_parent_tuple,
    document_file_catalog_link,
    document_file_owner_tuple,
)
from core.documents.catalog import DocumentCatalog
from core.files.models import FileRecord

OfficeLinkPermission = Literal["viewer", "editor"]
OfficeAccessResourceKind = Literal["catalog", "binding"]

_MEMBER_RELATIONS: tuple[AuthzRelation, ...] = (
    AuthzRelation.VIEWER,
    AuthzRelation.EDITOR,
)


@dataclass(frozen=True)
class PublicLinkTarget:
    kind: OfficeAccessResourceKind
    catalog: DocumentCatalog | None
    binding: FileRecord | None
    token_hash: str


class OfficeAccessService:
    def __init__(
        self,
        authz: AuthzService,
    ) -> None:
        self._authz: AuthzService = authz

    @staticmethod
    def build_public_page_url(origin: str, raw_token: str) -> str:
        base = origin.rstrip("/")
        if not base:
            raise ValueError("origin is required for a public link")
        return f"{base}/documents/p/{raw_token}"

    def _catalog_obj(self, catalog_id: str) -> AuthzObject:
        return AuthzObject.document_catalog(catalog_id)

    def _document_obj(self, file_id: str) -> AuthzObject:
        return AuthzObject.document_file(file_id)

    async def sync_catalog_created(
        self,
        catalog: DocumentCatalog,
        *,
        owner_user_id: str,
        company_visible: bool,
    ) -> None:
        writes: list[AuthzTuple] = [
            document_catalog_owner_tuple(catalog.catalog_id, owner_user_id),
            document_catalog_company_link(catalog.catalog_id, catalog.company_id),
        ]
        if catalog.parent_catalog_id is not None:
            writes.append(
                document_catalog_parent_tuple(catalog.catalog_id, catalog.parent_catalog_id)
            )
        if company_visible:
            writes.append(
                document_catalog_company_viewer_tuple(
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
        record: FileRecord,
        *,
        owner_user_id: str,
    ) -> None:
        if record.catalog_id is None:
            raise ValueError("file has no catalog")
        await self._authz.write(
            [
                document_file_owner_tuple(record.file_id, owner_user_id),
                document_file_catalog_link(record.file_id, record.catalog_id),
            ]
        )

    async def sync_document_moved(
        self,
        record: FileRecord,
        *,
        old_catalog_id: str,
    ) -> None:
        if record.catalog_id is None:
            raise ValueError("file has no catalog")
        if old_catalog_id == record.catalog_id:
            return
        await self._authz.write_and_delete(
            [document_file_catalog_link(record.file_id, record.catalog_id)],
            [document_file_catalog_link(record.file_id, old_catalog_id)],
        )

    async def sync_document_deleted(self, file_id: str) -> None:
        deletes = await self._authz.list_tuples(self._document_obj(file_id))
        if deletes:
            await self._authz.delete(deletes)

    async def set_catalog_company_visible(
        self,
        catalog: DocumentCatalog,
        *,
        company_visible: bool,
    ) -> None:
        link = document_catalog_company_link(catalog.catalog_id, catalog.company_id)
        viewer = document_catalog_company_viewer_tuple(
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

    async def ensure_catalog_authz(self, catalog: DocumentCatalog) -> None:
        """Дописывает owner/company/parent, если SQL-запись есть, а tuples нет."""
        existing = await self._authz.list_tuples(self._catalog_obj(catalog.catalog_id))
        relations = {item.relation for item in existing}
        writes: list[AuthzTuple] = []
        if AuthzRelation.OWNER not in relations:
            writes.append(
                document_catalog_owner_tuple(catalog.catalog_id, catalog.owner_user_id)
            )
        if AuthzRelation.COMPANY not in relations:
            writes.append(
                document_catalog_company_link(catalog.catalog_id, catalog.company_id)
            )
        if (
            catalog.parent_catalog_id is not None
            and AuthzRelation.PARENT not in relations
        ):
            writes.append(
                document_catalog_parent_tuple(catalog.catalog_id, catalog.parent_catalog_id)
            )
        if writes:
            await self._authz.write(writes)

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
        record: FileRecord,
        *,
        company_id: str,
        user_id: str,
    ) -> bool:
        if record.company_id != company_id or record.catalog_id is None:
            return False
        if record.deleted_at is not None:
            return False
        return await self._authz.can_view(self._document_obj(record.file_id), user_id=user_id)

    async def user_can_manage_trashed_binding(
        self,
        record: FileRecord,
        *,
        company_id: str,
        user_id: str,
    ) -> bool:
        if record.company_id != company_id or record.catalog_id is None:
            return False
        if record.deleted_at is None:
            return False
        return await self._authz.can_view(self._document_obj(record.file_id), user_id=user_id)

    async def list_accessible_catalogs_with_file_counts(
        self,
        *,
        company_id: str,
        namespace: str,
        user_id: str,
    ) -> list[tuple[DocumentCatalog, int]]:
        candidates = await DocumentCatalog.list_by_title_key_in_namespace(company_id, namespace)
        if not candidates:
            return []
        checks = [
            AuthzCheckItem(
                subject=AuthzSubject.user(user_id),
                relation=AuthzRelation.CAN_LIST,
                obj=self._catalog_obj(catalog.catalog_id),
                correlation_id=catalog.catalog_id,
            )
            for catalog in candidates
        ]
        allowed = await self._authz.batch_check(checks)
        result: list[tuple[DocumentCatalog, int]] = []
        for catalog, is_allowed in zip(candidates, allowed, strict=True):
            if not is_allowed:
                continue
            count = await FileRecord.count_in_catalog(catalog.catalog_id)
            result.append((catalog, count))
        return result

    async def binding_visible_in_public_catalog(
        self,
        binding: FileRecord,
    ) -> bool:
        if binding.deleted_at is not None or binding.catalog_id is None:
            return False
        link = await DocumentLink.for_target("file", binding.file_id)
        return link is not None and link.enabled

    async def resolve_public_token(self, raw_token: str) -> PublicLinkTarget:
        normalized = raw_token.strip()
        if normalized == "":
            raise ValueError("token is required")
        token_hash = hash_token(normalized)
        link = await DocumentLink.by_enabled_token(token_hash)
        if link is None:
            raise ValueError("Link not found")
        if link.target_kind == "file":
            record = await FileRecord.get(link.target_id)
            if record is None or record.deleted_at is not None:
                raise ValueError("Link not found")
            return PublicLinkTarget(
                kind="binding",
                catalog=None,
                binding=record,
                token_hash=token_hash,
            )
        catalog = await DocumentCatalog.get(link.target_id)
        if catalog is None:
            raise ValueError("Link not found")
        return PublicLinkTarget(
            kind="catalog",
            catalog=catalog,
            binding=None,
            token_hash=token_hash,
        )

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
    ) -> OfficeResourceAccessResponse:
        catalog = await DocumentCatalog.catalog_in_namespace(catalog_id, company_id, namespace)
        if catalog is None:
            raise ValueError("Catalog not found")
        members = await self._list_member_items(self._catalog_obj(catalog_id))
        link = await DocumentLink.for_target("catalog", catalog_id)
        return OfficeResourceAccessResponse(
            resource_kind="catalog",
            resource_id=catalog_id,
            company_visible=await self.catalog_is_company_visible(catalog_id, company_id),
            link_enabled=link.enabled if link is not None else False,
            link_permission=_parse_link_permission(link.permission if link is not None else "viewer"),
            public_url=None,
            members=members,
        )

    async def get_binding_access(
        self,
        binding: FileRecord,
    ) -> OfficeResourceAccessResponse:
        members = await self._list_member_items(self._document_obj(binding.file_id))
        if binding.catalog_id is None or binding.company_id is None:
            raise ValueError("file has no catalog")
        company_visible = await self.catalog_is_company_visible(
            binding.catalog_id, binding.company_id
        )
        link = await DocumentLink.for_target("file", binding.file_id)
        return OfficeResourceAccessResponse(
            resource_kind="binding",
            resource_id=binding.file_id,
            company_visible=company_visible,
            link_enabled=link.enabled if link is not None else False,
            link_permission=_parse_link_permission(link.permission if link is not None else "viewer"),
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
        origin: str,
    ) -> tuple[OfficeResourceAccessResponse, str | None]:
        catalog = await DocumentCatalog.catalog_in_namespace(catalog_id, company_id, namespace)
        if catalog is None:
            raise ValueError("Catalog not found")
        raw_token: str | None = None
        current = await DocumentLink.ensure(
            company_id=company_id,
            target_kind="catalog",
            target_id=catalog_id,
            created_by_user_id=catalog.owner_user_id,
        )
        link_enabled = current.enabled
        link_token_hash = current.token_hash
        link_permission = current.permission
        if body.company_visible is not None:
            await self.set_catalog_company_visible(catalog, company_visible=body.company_visible)
            if body.company_visible and body.members:
                raise ValueError(
                    "Company-visible catalog is available to the whole company; members are not set"
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
        _ = await DocumentLink.update_enabled_token_hash_and_permission(
            current,
            enabled=link_enabled,
            token_hash=link_token_hash,
            permission=link_permission,
        )
        if body.members is not None:
            if await self.catalog_is_company_visible(catalog_id, company_id):
                if body.members:
                    raise ValueError(
                        "Company-visible catalog is available to the whole company in this workspace"
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
        response = await self.get_catalog_access(catalog_id, company_id, namespace)
        if raw_token is not None:
            response = response.model_copy(
                update={"public_url": self.build_public_page_url(origin, raw_token)},
            )
        return response, raw_token

    async def patch_binding_access(
        self,
        binding: FileRecord,
        body: OfficeResourceAccessPatchRequest,
        origin: str,
    ) -> tuple[OfficeResourceAccessResponse, str | None]:
        raw_token: str | None = None
        if binding.company_id is None or binding.uploaded_by is None:
            raise ValueError("file has no owner")
        current = await DocumentLink.ensure(
            company_id=binding.company_id,
            target_kind="file",
            target_id=binding.file_id,
            created_by_user_id=binding.uploaded_by,
        )
        link_enabled = current.enabled
        link_token_hash = current.token_hash
        link_permission = current.permission
        if body.company_visible is not None:
            raise ValueError("company_visible is set on the catalog, not on the document")
        if body.link_enabled is not None:
            link_enabled = body.link_enabled
            if link_enabled:
                if link_token_hash is None:
                    raw_token, link_token_hash = create_share_token()
            else:
                link_token_hash = None
        if body.link_permission is not None:
            link_permission = body.link_permission
        _ = await DocumentLink.update_enabled_token_hash_and_permission(
            current,
            enabled=link_enabled,
            token_hash=link_token_hash,
            permission=link_permission,
        )
        updated_binding = binding
        if body.members is not None:
            await self._replace_members(
                self._document_obj(binding.file_id),
                members=[(row.user_id, _member_to_relation(row.relation)) for row in body.members],
                owner_user_id=binding.uploaded_by,
            )
        response = await self.get_binding_access(updated_binding)
        if raw_token is not None:
            response = response.model_copy(
                update={"public_url": self.build_public_page_url(origin, raw_token)},
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
        catalog = await DocumentCatalog.catalog_in_namespace(catalog_id, company_id, namespace)
        if catalog is None:
            raise ValueError("Catalog not found")
        if await self.catalog_is_company_visible(catalog_id, company_id):
            raise ValueError("Company-visible catalog is available to the whole company in this workspace")
        owner_user_id = await self.resolve_catalog_owner_user_id(catalog_id)
        if user_id == owner_user_id:
            raise ValueError("Owner already has full access to the catalog")
        await self._authz.write([document_catalog_member_tuple(catalog_id, user_id, relation)])

    async def remove_catalog_member(self, catalog_id: str, user_id: str) -> None:
        owner_user_id = await self.resolve_catalog_owner_user_id(catalog_id)
        if user_id == owner_user_id:
            raise ValueError("Cannot remove the owner from members")
        await self._authz.delete(
            [
                document_catalog_member_tuple(catalog_id, user_id, AuthzRelation.VIEWER),
                document_catalog_member_tuple(catalog_id, user_id, AuthzRelation.EDITOR),
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
        origin: str,
    ) -> OfficeResourceAccessRotateLinkResponse:
        catalog = await DocumentCatalog.catalog_in_namespace(catalog_id, company_id, namespace)
        if catalog is None:
            raise ValueError("Catalog not found")
        link = await DocumentLink.for_target("catalog", catalog_id)
        if link is None or not link.enabled:
            raise ValueError("Public link is not enabled")
        raw_token, token_hash = create_share_token()
        _ = await DocumentLink.update_enabled_token_hash_and_permission(
            link,
            enabled=True,
            token_hash=token_hash,
            permission=link.permission,
        )
        return OfficeResourceAccessRotateLinkResponse(
            public_url=self.build_public_page_url(origin, raw_token),
        )

    async def rotate_binding_link(
        self,
        binding: FileRecord,
        origin: str,
    ) -> OfficeResourceAccessRotateLinkResponse:
        link = await DocumentLink.for_target("file", binding.file_id)
        if link is None or not link.enabled:
            raise ValueError("Public link is not enabled")
        raw_token, token_hash = create_share_token()
        _ = await DocumentLink.update_enabled_token_hash_and_permission(
            link,
            enabled=True,
            token_hash=token_hash,
            permission=link.permission,
        )
        return OfficeResourceAccessRotateLinkResponse(
            public_url=self.build_public_page_url(origin, raw_token),
        )

    async def build_public_resolve(self, target: PublicLinkTarget) -> OfficePublicResolveResponse:
        if target.kind == "binding":
            binding = target.binding
            if binding is None:
                raise ValueError("binding is required")
            link = await DocumentLink.for_target("file", binding.file_id)
            permission = link.permission if link is not None else "viewer"
            return OfficePublicResolveResponse(
                resource_kind="binding",
                resource_id=binding.file_id,
                title=document_title(binding),
                link_permission=_parse_link_permission(permission),
                file_id=binding.file_id,
                catalog_id=binding.catalog_id,
            )
        catalog = target.catalog
        if catalog is None:
            raise ValueError("catalog is required")
        link = await DocumentLink.for_target("catalog", catalog.catalog_id)
        permission = link.permission if link is not None else "viewer"
        return OfficePublicResolveResponse(
            resource_kind="catalog",
            resource_id=catalog.catalog_id,
            title=catalog.title,
            link_permission=_parse_link_permission(permission),
            file_id=None,
            catalog_id=catalog.catalog_id,
        )

    async def list_public_catalog_items(
        self, target: PublicLinkTarget
    ) -> OfficePublicCatalogItemsResponse:
        if target.kind != "catalog" or target.catalog is None:
            raise ValueError("Token does not belong to the catalog")
        catalog = target.catalog
        bindings = await FileRecord.alive_in_catalog(
            company_id=catalog.company_id,
            catalog_id=catalog.catalog_id,
        )
        items: list[OfficePublicCatalogItem] = []
        for binding in bindings:
            if not await self.binding_visible_in_public_catalog(binding):
                continue
            file_category, onlyoffice_document_type = resolve_binding_metadata(
                binding.original_name,
                binding.content_type.split(";", 1)[0].strip(),
            )
            link = await DocumentLink.for_target("file", binding.file_id)
            permission = link.permission if link is not None else "viewer"
            items.append(
                OfficePublicCatalogItem(
                    title=document_title(binding),
                    file_id=binding.file_id,
                    file_category=file_category,
                    onlyoffice_document_type=onlyoffice_document_type,
                    link_permission=_parse_link_permission(permission),
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
    ) -> FileRecord:
        if catalog_target.kind != "catalog" or catalog_target.catalog is None:
            raise ValueError("Token does not belong to the catalog")
        catalog = catalog_target.catalog
        binding = await FileRecord.by_file_id(file_id, catalog.company_id)
        if binding is None or binding.deleted_at is not None:
            raise ValueError("File not found")
        if binding.catalog_id != catalog.catalog_id:
            raise ValueError("File does not belong to the catalog")
        if not await self.binding_visible_in_public_catalog(binding):
            raise ValueError("File is not available via the public link")
        return binding


def _parse_link_permission(value: str) -> OfficeLinkPermission:
    if value == "editor":
        return "editor"
    if value == "viewer":
        return "viewer"
    raise ValueError(f"Unknown link_permission: {value}")


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
