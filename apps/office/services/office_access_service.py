"""Единая модель доступа: company, members, public link для catalog и binding."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

from fastapi import Request

from apps.office.db.models import OfficeDocumentBinding, OfficeDocumentCatalog
from apps.office.db.repositories.access_repository import OfficeAccessRepository
from apps.office.db.repositories.catalog_repository import CatalogRepository
from apps.office.db.repositories.document_binding_repository import DocumentBindingRepository
from apps.office.models.api import (
    OfficePublicCatalogItem,
    OfficePublicCatalogItemsResponse,
    OfficePublicResolveResponse,
    OfficeResourceAccessMemberItem,
    OfficeResourceAccessPatchRequest,
    OfficeResourceAccessResponse,
    OfficeResourceAccessRotateLinkResponse,
)
from apps.office.services.public_link_tokens import create_share_token

OfficeLinkPermission = Literal["view", "edit"]
OfficeAccessResourceKind = Literal["catalog", "binding"]


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
    ) -> None:
        self._catalog_repository: CatalogRepository = catalog_repository
        self._binding_repository: DocumentBindingRepository = document_binding_repository
        self._access_repository: OfficeAccessRepository = access_repository

    @staticmethod
    def hash_link_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    @staticmethod
    def build_public_page_url(request: Request, raw_token: str) -> str:
        base = str(request.base_url).rstrip("/")
        return f"{base}/documents/p/{raw_token}"

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

    async def _user_has_binding_management_access(
        self,
        binding: OfficeDocumentBinding,
        *,
        company_id: str,
        namespace: str,
        user_id: str,
    ) -> bool:
        if await self._catalog_repository.user_can_access_catalog(
            binding.catalog_id,
            company_id,
            namespace,
            user_id,
        ):
            return True
        if await self._access_repository.user_is_binding_member(binding.binding_id, user_id):
            return True
        if binding.created_by_user_id == user_id:
            return True
        return False

    async def user_can_view_binding(
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
        return await self._user_has_binding_management_access(
            binding,
            company_id=company_id,
            namespace=namespace,
            user_id=user_id,
        )

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
        return await self._user_has_binding_management_access(
            binding,
            company_id=company_id,
            namespace=namespace,
            user_id=user_id,
        )

    async def binding_visible_in_public_catalog(
        self,
        binding: OfficeDocumentBinding,
    ) -> bool:
        if binding.deleted_at is not None:
            return False
        return binding.link_enabled

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
        members = await self._catalog_repository.list_members(catalog_id)
        return OfficeResourceAccessResponse(
            resource_kind="catalog",
            resource_id=catalog_id,
            company_visible=catalog.is_public,
            link_enabled=catalog.link_enabled,
            link_permission=_parse_link_permission(catalog.link_permission),
            public_url=None,
            members=[
                OfficeResourceAccessMemberItem(user_id=member.user_id)
                for member in members
            ],
        )

    async def get_binding_access(
        self,
        binding: OfficeDocumentBinding,
        _request: Request,
    ) -> OfficeResourceAccessResponse:
        members = await self._access_repository.list_binding_members(binding.binding_id)
        catalog = await self._catalog_repository.get(
            binding.catalog_id,
            binding.company_id,
            binding.namespace,
        )
        company_visible = catalog.is_public if catalog is not None else False
        return OfficeResourceAccessResponse(
            resource_kind="binding",
            resource_id=binding.binding_id,
            company_visible=company_visible,
            link_enabled=binding.link_enabled,
            link_permission=_parse_link_permission(binding.link_permission),
            public_url=None,
            members=[
                OfficeResourceAccessMemberItem(user_id=member.user_id)
                for member in members
            ],
        )

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
            updated = await self._catalog_repository.update_catalog(
                catalog_id,
                company_id,
                namespace,
                is_public=body.company_visible,
            )
            if updated is None:
                raise ValueError("Каталог не найден")
            link_enabled = updated.link_enabled
            link_token_hash = updated.link_token_hash
            link_permission = updated.link_permission
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
        if body.member_user_ids is not None:
            if updated_catalog.is_public:
                raise ValueError("Публичный каталог доступен всей компании в этом пространстве")
            existing = await self._catalog_repository.list_members(catalog_id)
            existing_ids = {row.user_id for row in existing}
            desired_ids = set(body.member_user_ids)
            for uid in existing_ids - desired_ids:
                _ = await self._catalog_repository.remove_member(catalog_id, uid)
            for uid in desired_ids - existing_ids:
                if uid == updated_catalog.owner_user_id:
                    continue
                _ = await self._catalog_repository.add_member(
                    catalog_id,
                    uid,
                    company_id=company_id,
                    namespace=namespace,
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
        if body.link_enabled is not None:
            link_enabled = body.link_enabled
            if link_enabled:
                if link_token_hash is None:
                    raw_token, link_token_hash = create_share_token()
            else:
                link_token_hash = None
        if body.link_permission is not None:
            link_permission = body.link_permission
        updated_binding = await self._access_repository.set_binding_link(
            binding.binding_id,
            link_enabled=link_enabled,
            link_token_hash=link_token_hash,
            link_permission=link_permission,
        )
        if updated_binding is None:
            raise ValueError("Привязка не найдена")
        if body.member_user_ids is not None:
            existing = await self._access_repository.list_binding_members(binding.binding_id)
            existing_ids = {row.user_id for row in existing}
            desired_ids = set(body.member_user_ids)
            for uid in existing_ids - desired_ids:
                _ = await self._access_repository.remove_binding_member(binding.binding_id, uid)
            for uid in desired_ids - existing_ids:
                if uid == binding.created_by_user_id:
                    continue
                _ = await self._access_repository.add_binding_member(binding.binding_id, uid)
        response = await self.get_binding_access(updated_binding, request)
        if raw_token is not None:
            response = response.model_copy(
                update={"public_url": self.build_public_page_url(request, raw_token)},
            )
        return response, raw_token

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
        updated = await self._access_repository.set_binding_link(
            binding.binding_id,
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
                resource_id=binding.binding_id,
                title=binding.title,
                link_permission=_parse_link_permission(binding.link_permission),
                file_id=binding.file_id,
                catalog_id=binding.catalog_id,
                binding_id=binding.binding_id,
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
            binding_id=None,
        )

    async def list_public_catalog_items(self, target: PublicLinkTarget) -> OfficePublicCatalogItemsResponse:
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
                    binding_id=binding.binding_id,
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
        binding_id: str,
    ) -> OfficeDocumentBinding:
        if catalog_target.kind != "catalog" or catalog_target.catalog is None:
            raise ValueError("Токен не относится к каталогу")
        catalog = catalog_target.catalog
        binding = await self._binding_repository.get_for_company(
            binding_id,
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
    if value == "edit":
        return "edit"
    if value == "view":
        return "view"
    raise ValueError(f"Неизвестное link_permission: {value}")
