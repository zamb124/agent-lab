"""Idempotent Office catalog path + document bind."""

from __future__ import annotations

from datetime import datetime, timezone

from apps.office.db.models import OfficeDocumentBinding, OfficeDocumentCatalog
from apps.office.services.file_binding_metadata import resolve_binding_metadata
from apps.office.services.office_access_service import OfficeAccessService
from core.documents.placement import DocsBindResult, DocsPlacement
from core.documents.placement_paths import build_path_segments
from core.files.create_spec import FileSourceKind
from core.files.retention import FileRetentionKind
from core.files.service import FilesService


class DocsPlacementService:
    def __init__(
        self,
        *,
        files_service: FilesService,
        office_access_service: OfficeAccessService,
    ) -> None:
        self._files_service: FilesService = files_service
        self._office_access_service: OfficeAccessService = office_access_service

    async def bind(self, placement: DocsPlacement, *, company_id: str, user_id: str) -> DocsBindResult:
        record = await self._files_service.get(placement.file_id)
        if record.company_id != company_id:
            raise ValueError("file does not belong to company")

        existing = await OfficeDocumentBinding.binding_in_namespace(
            placement.file_id,
            company_id,
            placement.namespace,
        )
        if existing is not None:
            _ = await self._files_service.promote_retention(
                placement.file_id,
                retention_kind=FileRetentionKind.OFFICE_DOCUMENT,
                source_kind=FileSourceKind.OFFICE_DOCUMENT,
            )
            return DocsBindResult(
                file_id=existing.file_id,
                catalog_id=existing.catalog_id,
                created=False,
                catalog_path=[],
            )

        segments = placement.path_segments
        if segments is None:
            if placement.anchor is None:
                raise ValueError("path_segments or anchor required")
            segments = build_path_segments(placement.anchor)

        catalog_id = await self.ensure_catalog_path(
            company_id=company_id,
            namespace=placement.namespace,
            segments=segments,
            user_id=user_id,
        )

        title = placement.title if placement.title else record.original_name
        file_category, onlyoffice_document_type = resolve_binding_metadata(
            record.original_name,
            record.content_type.split(";", 1)[0].strip(),
        )
        now = datetime.now(timezone.utc)
        row = await OfficeDocumentBinding.create_binding(
            OfficeDocumentBinding(
                file_id=placement.file_id,
                company_id=company_id,
                namespace=placement.namespace,
                catalog_id=catalog_id,
                file_category=file_category,
                onlyoffice_document_type=onlyoffice_document_type,
                title=title,
                created_by_user_id=user_id,
                created_at=now,
                updated_at=now,
            )
        )
        try:
            await self._office_access_service.sync_document_created(
                row,
                owner_user_id=user_id,
            )
        except Exception:
            _ = await OfficeDocumentBinding.delete_binding_in_namespace(
                row.file_id,
                company_id,
                placement.namespace,
            )
            raise
        _ = await self._files_service.promote_retention(
            placement.file_id,
            retention_kind=FileRetentionKind.OFFICE_DOCUMENT,
            source_kind=FileSourceKind.OFFICE_DOCUMENT,
        )
        return DocsBindResult(
            file_id=row.file_id,
            catalog_id=row.catalog_id,
            created=True,
            catalog_path=segments,
        )

    async def ensure_catalog_path(
        self,
        *,
        company_id: str,
        namespace: str,
        segments: list[str],
        user_id: str,
    ) -> str:
        parent_id: str | None = None
        for segment in segments:
            catalog, created = await OfficeDocumentCatalog.ensure_child_catalog(
                company_id=company_id,
                namespace=namespace,
                parent_catalog_id=parent_id,
                title=segment.strip(),
                owner_user_id=user_id,
            )
            if created:
                try:
                    await self._office_access_service.sync_catalog_created(
                        catalog,
                        owner_user_id=user_id,
                        company_visible=True,
                    )
                except Exception:
                    _ = await OfficeDocumentCatalog.delete_catalog_in_namespace(
                        catalog.catalog_id,
                        company_id,
                        namespace,
                    )
                    raise
            else:
                await self._office_access_service.ensure_catalog_authz(catalog)
            parent_id = catalog.catalog_id
        if parent_id is None:
            raise ValueError("empty path segments")
        return parent_id
