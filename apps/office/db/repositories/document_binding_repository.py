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
                )
                .order_by(OfficeDocumentBinding.created_at.desc())
            )
            return list(result.scalars().all())

    async def list_by_company_namespace_and_catalogs(
        self, company_id: str, namespace: str, catalog_ids: list[str]
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
                )
                .order_by(OfficeDocumentBinding.created_at.desc())
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
        document_type: str,
        title: str,
        created_by_user_id: str,
    ) -> OfficeDocumentBinding:
        binding_id = uuid.uuid4().hex
        row = OfficeDocumentBinding(
            binding_id=binding_id,
            company_id=company_id,
            namespace=namespace,
            catalog_id=catalog_id,
            file_id=file_id,
            document_type=document_type,
            title=title,
            created_by_user_id=created_by_user_id,
            created_at=datetime.now(timezone.utc),
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
