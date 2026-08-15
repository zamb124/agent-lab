"""Репозиторий public link (AuthN). ACL members — только OpenFGA."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from apps.office.db.base import OfficeDatabase
from apps.office.db.models import OfficeDocumentBinding, OfficeDocumentCatalog


class OfficeAccessRepository:
    def __init__(self, db: OfficeDatabase) -> None:
        self._db: OfficeDatabase = db

    async def get_catalog_by_link_token_hash(
        self,
        token_hash: str,
    ) -> OfficeDocumentCatalog | None:
        async with self._db.session() as session:
            result = await session.execute(
                select(OfficeDocumentCatalog).where(
                    OfficeDocumentCatalog.link_token_hash == token_hash,
                    OfficeDocumentCatalog.link_enabled.is_(True),
                )
            )
            return result.scalar_one_or_none()

    async def get_binding_by_link_token_hash(
        self,
        token_hash: str,
    ) -> OfficeDocumentBinding | None:
        async with self._db.session() as session:
            result = await session.execute(
                select(OfficeDocumentBinding).where(
                    OfficeDocumentBinding.link_token_hash == token_hash,
                    OfficeDocumentBinding.link_enabled.is_(True),
                    OfficeDocumentBinding.deleted_at.is_(None),
                )
            )
            return result.scalar_one_or_none()

    async def set_catalog_link(
        self,
        catalog_id: str,
        company_id: str,
        namespace: str,
        *,
        link_enabled: bool,
        link_token_hash: str | None,
        link_permission: str,
    ) -> OfficeDocumentCatalog | None:
        async with self._db.session() as session:
            result = await session.execute(
                select(OfficeDocumentCatalog).where(
                    OfficeDocumentCatalog.catalog_id == catalog_id,
                    OfficeDocumentCatalog.company_id == company_id,
                    OfficeDocumentCatalog.namespace == namespace,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            row.link_enabled = link_enabled
            row.link_token_hash = link_token_hash
            row.link_permission = link_permission
            row.link_updated_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(row)
            return row

    async def set_document_link(
        self,
        file_id: str,
        *,
        link_enabled: bool,
        link_token_hash: str | None,
        link_permission: str,
    ) -> OfficeDocumentBinding | None:
        async with self._db.session() as session:
            result = await session.execute(
                select(OfficeDocumentBinding).where(
                    OfficeDocumentBinding.file_id == file_id,
                    OfficeDocumentBinding.deleted_at.is_(None),
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            row.link_enabled = link_enabled
            row.link_token_hash = link_token_hash
            row.link_permission = link_permission
            row.link_updated_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(row)
            return row
