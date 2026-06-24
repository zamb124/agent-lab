"""
Репозиторий привязок документов OnlyOffice к компании и namespace.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from apps.office.db.base import OfficeDatabase
from apps.office.db.models import OfficeDocumentBinding


class DocumentBindingRepository:
    def __init__(self, db: OfficeDatabase) -> None:
        self._db: OfficeDatabase = db

    def _active_filter(self):
        return OfficeDocumentBinding.deleted_at.is_(None)

    async def list_by_company_namespace_and_catalog(
        self, company_id: str, namespace: str, catalog_id: str
    ) -> list[OfficeDocumentBinding]:
        async with self._db.session() as session:
            result = await session.execute(
                select(OfficeDocumentBinding)
                .where(
                    OfficeDocumentBinding.company_id == company_id,
                    OfficeDocumentBinding.namespace == namespace,
                    OfficeDocumentBinding.catalog_id == catalog_id,
                    self._active_filter(),
                )
                .order_by(OfficeDocumentBinding.created_at.desc())
            )
            return list(result.scalars().all())

    async def list_by_company_namespace_and_catalogs(
        self,
        company_id: str,
        namespace: str,
        catalog_ids: list[str],
    ) -> list[OfficeDocumentBinding]:
        if not catalog_ids:
            return []
        async with self._db.session() as session:
            result = await session.execute(
                select(OfficeDocumentBinding)
                .where(
                    OfficeDocumentBinding.company_id == company_id,
                    OfficeDocumentBinding.namespace == namespace,
                    OfficeDocumentBinding.catalog_id.in_(catalog_ids),
                    self._active_filter(),
                )
                .order_by(OfficeDocumentBinding.created_at.desc())
            )
            return list(result.scalars().all())

    async def list_deleted_by_namespace(
        self, company_id: str, namespace: str
    ) -> list[OfficeDocumentBinding]:
        async with self._db.session() as session:
            result = await session.execute(
                select(OfficeDocumentBinding)
                .where(
                    OfficeDocumentBinding.company_id == company_id,
                    OfficeDocumentBinding.namespace == namespace,
                    OfficeDocumentBinding.deleted_at.is_not(None),
                )
                .order_by(OfficeDocumentBinding.deleted_at.desc())
            )
            return list(result.scalars().all())

    async def search_by_title(
        self, company_id: str, namespace: str, query: str, limit: int = 100
    ) -> list[OfficeDocumentBinding]:
        needle = query.strip().casefold()
        if needle == "":
            return []
        async with self._db.session() as session:
            result = await session.execute(
                select(OfficeDocumentBinding)
                .where(
                    OfficeDocumentBinding.company_id == company_id,
                    OfficeDocumentBinding.namespace == namespace,
                    self._active_filter(),
                )
                .order_by(OfficeDocumentBinding.updated_at.desc())
                .limit(limit)
            )
            rows = list(result.scalars().all())
        return [row for row in rows if needle in row.title.casefold()]

    async def list_by_binding_ids(
        self, company_id: str, namespace: str, binding_ids: list[str]
    ) -> list[OfficeDocumentBinding]:
        if not binding_ids:
            return []
        async with self._db.session() as session:
            result = await session.execute(
                select(OfficeDocumentBinding)
                .where(
                    OfficeDocumentBinding.company_id == company_id,
                    OfficeDocumentBinding.namespace == namespace,
                    OfficeDocumentBinding.binding_id.in_(binding_ids),
                    self._active_filter(),
                )
                .order_by(OfficeDocumentBinding.updated_at.desc())
            )
            return list(result.scalars().all())

    async def get_for_company(
        self, binding_id: str, company_id: str, namespace: str
    ) -> OfficeDocumentBinding | None:
        async with self._db.session() as session:
            result = await session.execute(
                select(OfficeDocumentBinding).where(
                    OfficeDocumentBinding.binding_id == binding_id,
                    OfficeDocumentBinding.company_id == company_id,
                    OfficeDocumentBinding.namespace == namespace,
                )
            )
            return result.scalar_one_or_none()

    async def get_by_binding_and_company(
        self, binding_id: str, company_id: str
    ) -> OfficeDocumentBinding | None:
        async with self._db.session() as session:
            result = await session.execute(
                select(OfficeDocumentBinding).where(
                    OfficeDocumentBinding.binding_id == binding_id,
                    OfficeDocumentBinding.company_id == company_id,
                )
            )
            return result.scalar_one_or_none()

    async def get_by_file_for_company(
        self,
        file_id: str,
        company_id: str,
        namespace: str,
    ) -> OfficeDocumentBinding | None:
        async with self._db.session() as session:
            result = await session.execute(
                select(OfficeDocumentBinding)
                .where(
                    OfficeDocumentBinding.file_id == file_id,
                    OfficeDocumentBinding.company_id == company_id,
                    OfficeDocumentBinding.namespace == namespace,
                    self._active_filter(),
                )
                .order_by(OfficeDocumentBinding.created_at.desc())
            )
            return result.scalar_one_or_none()

    async def create(
        self,
        *,
        company_id: str,
        namespace: str,
        catalog_id: str,
        file_id: str,
        file_category: str,
        onlyoffice_document_type: str | None,
        title: str,
        created_by_user_id: str,
    ) -> OfficeDocumentBinding:
        binding_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc)
        row = OfficeDocumentBinding(
            binding_id=binding_id,
            company_id=company_id,
            namespace=namespace,
            catalog_id=catalog_id,
            file_id=file_id,
            file_category=file_category,
            onlyoffice_document_type=onlyoffice_document_type,
            title=title,
            created_by_user_id=created_by_user_id,
            created_at=now,
            updated_at=now,
        )
        async with self._db.session() as session:
            session.add(row)
            await session.commit()
            await session.refresh(row)
        return row

    async def update_title(
        self,
        binding_id: str,
        company_id: str,
        namespace: str,
        title: str,
    ) -> OfficeDocumentBinding | None:
        async with self._db.session() as session:
            result = await session.execute(
                select(OfficeDocumentBinding).where(
                    OfficeDocumentBinding.binding_id == binding_id,
                    OfficeDocumentBinding.company_id == company_id,
                    OfficeDocumentBinding.namespace == namespace,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            row.title = title
            row.updated_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(row)
            return row

    async def soft_delete(
        self,
        binding_id: str,
        company_id: str,
        namespace: str,
        deleted_by_user_id: str,
    ) -> bool:
        async with self._db.session() as session:
            result = await session.execute(
                select(OfficeDocumentBinding).where(
                    OfficeDocumentBinding.binding_id == binding_id,
                    OfficeDocumentBinding.company_id == company_id,
                    OfficeDocumentBinding.namespace == namespace,
                    self._active_filter(),
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return False
            row.deleted_at = datetime.now(timezone.utc)
            row.deleted_by_user_id = deleted_by_user_id
            row.updated_at = datetime.now(timezone.utc)
            await session.commit()
            return True

    async def restore(
        self, binding_id: str, company_id: str, namespace: str
    ) -> OfficeDocumentBinding | None:
        async with self._db.session() as session:
            result = await session.execute(
                select(OfficeDocumentBinding).where(
                    OfficeDocumentBinding.binding_id == binding_id,
                    OfficeDocumentBinding.company_id == company_id,
                    OfficeDocumentBinding.namespace == namespace,
                    OfficeDocumentBinding.deleted_at.is_not(None),
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            row.deleted_at = None
            row.deleted_by_user_id = None
            row.updated_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(row)
            return row

    async def move_to_catalog(
        self,
        binding_id: str,
        company_id: str,
        namespace: str,
        catalog_id: str,
    ) -> OfficeDocumentBinding | None:
        async with self._db.session() as session:
            result = await session.execute(
                select(OfficeDocumentBinding).where(
                    OfficeDocumentBinding.binding_id == binding_id,
                    OfficeDocumentBinding.company_id == company_id,
                    OfficeDocumentBinding.namespace == namespace,
                    self._active_filter(),
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            row.catalog_id = catalog_id
            row.updated_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(row)
            return row

    async def delete_binding(
        self, binding_id: str, company_id: str, namespace: str
    ) -> bool:
        async with self._db.session() as session:
            result = await session.execute(
                select(OfficeDocumentBinding).where(
                    OfficeDocumentBinding.binding_id == binding_id,
                    OfficeDocumentBinding.company_id == company_id,
                    OfficeDocumentBinding.namespace == namespace,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True
