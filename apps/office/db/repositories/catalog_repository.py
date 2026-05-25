"""
Каталоги документов и участники (ACL).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import exists, func, or_, select

from apps.office.db.base import OfficeDatabase
from apps.office.db.models import OfficeCatalogMember, OfficeDocumentBinding, OfficeDocumentCatalog


class CatalogRepository:
    def __init__(self, db: OfficeDatabase) -> None:
        self._db: OfficeDatabase = db

    async def get_or_create_default(
        self,
        *,
        company_id: str,
        namespace: str,
        owner_user_id: str,
    ) -> OfficeDocumentCatalog:
        async with self._db.session() as session:
            result = await session.execute(
                select(OfficeDocumentCatalog)
                .where(
                    OfficeDocumentCatalog.company_id == company_id,
                    OfficeDocumentCatalog.namespace == namespace,
                    OfficeDocumentCatalog.owner_user_id == owner_user_id,
                )
                .order_by(OfficeDocumentCatalog.created_at.asc())
                .limit(1)
            )
            existing = result.scalar_one_or_none()
            if existing is not None:
                return existing
            catalog_id = uuid.uuid4().hex
            row = OfficeDocumentCatalog(
                catalog_id=catalog_id,
                company_id=company_id,
                namespace=namespace,
                title="Общие",
                owner_user_id=owner_user_id,
                is_public=True,
                created_at=datetime.now(timezone.utc),
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

    async def get(
        self, catalog_id: str, company_id: str, namespace: str
    ) -> OfficeDocumentCatalog | None:
        async with self._db.session() as session:
            result = await session.execute(
                select(OfficeDocumentCatalog).where(
                    OfficeDocumentCatalog.catalog_id == catalog_id,
                    OfficeDocumentCatalog.company_id == company_id,
                    OfficeDocumentCatalog.namespace == namespace,
                )
            )
            return result.scalar_one_or_none()

    async def user_can_access_catalog(
        self,
        catalog_id: str,
        company_id: str,
        namespace: str,
        user_id: str,
    ) -> bool:
        cat = await self.get(catalog_id, company_id, namespace)
        if cat is None:
            return False
        if cat.is_public:
            return True
        if cat.owner_user_id == user_id:
            return True
        async with self._db.session() as session:
            result = await session.execute(
                select(OfficeCatalogMember).where(
                    OfficeCatalogMember.catalog_id == catalog_id,
                    OfficeCatalogMember.user_id == user_id,
                )
            )
            return result.scalar_one_or_none() is not None

    async def user_is_owner(
        self,
        catalog_id: str,
        company_id: str,
        namespace: str,
        user_id: str,
    ) -> bool:
        cat = await self.get(catalog_id, company_id, namespace)
        if cat is None:
            return False
        return cat.owner_user_id == user_id

    async def list_accessible_with_file_counts(
        self,
        *,
        company_id: str,
        namespace: str,
        user_id: str,
    ) -> list[tuple[OfficeDocumentCatalog, int]]:
        member_exists = exists(
            select(1)
            .select_from(OfficeCatalogMember)
            .where(
                OfficeCatalogMember.catalog_id == OfficeDocumentCatalog.catalog_id,
                OfficeCatalogMember.user_id == user_id,
            )
        )
        async with self._db.session() as session:
            result = await session.execute(
                select(OfficeDocumentCatalog)
                .where(
                    OfficeDocumentCatalog.company_id == company_id,
                    OfficeDocumentCatalog.namespace == namespace,
                    or_(
                        OfficeDocumentCatalog.is_public.is_(True),
                        OfficeDocumentCatalog.owner_user_id == user_id,
                        member_exists,
                    ),
                )
                .order_by(OfficeDocumentCatalog.created_at.asc())
            )
            catalogs = list(result.scalars().all())
        return [(catalog, await self.count_bindings(catalog.catalog_id)) for catalog in catalogs]

    async def create(
        self,
        *,
        company_id: str,
        namespace: str,
        title: str,
        owner_user_id: str,
        is_public: bool = True,
    ) -> OfficeDocumentCatalog:
        catalog_id = uuid.uuid4().hex
        row = OfficeDocumentCatalog(
            catalog_id=catalog_id,
            company_id=company_id,
            namespace=namespace,
            title=title.strip(),
            owner_user_id=owner_user_id,
            is_public=is_public,
            created_at=datetime.now(timezone.utc),
        )
        async with self._db.session() as session:
            session.add(row)
            await session.commit()
            await session.refresh(row)
        return row

    async def update_catalog(
        self,
        catalog_id: str,
        company_id: str,
        namespace: str,
        *,
        title: str | None = None,
        is_public: bool | None = None,
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
            if title is not None:
                row.title = title.strip()
            if is_public is not None:
                row.is_public = is_public
            await session.commit()
            await session.refresh(row)
            return row

    async def count_bindings(self, catalog_id: str) -> int:
        async with self._db.session() as session:
            result = await session.execute(
                select(func.count(OfficeDocumentBinding.binding_id)).where(
                    OfficeDocumentBinding.catalog_id == catalog_id
                )
            )
            return int(result.scalar_one())

    async def delete_catalog(
        self,
        catalog_id: str,
        company_id: str,
        namespace: str,
    ) -> bool:
        if await self.count_bindings(catalog_id) > 0:
            raise ValueError("В каталоге есть документы")
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
                return False
            await session.delete(row)
            await session.commit()
            return True

    async def list_members(self, catalog_id: str) -> list[OfficeCatalogMember]:
        async with self._db.session() as session:
            result = await session.execute(
                select(OfficeCatalogMember).where(
                    OfficeCatalogMember.catalog_id == catalog_id
                )
            )
            return list(result.scalars().all())

    async def add_member(
        self,
        catalog_id: str,
        user_id: str,
        *,
        company_id: str,
        namespace: str,
    ) -> OfficeCatalogMember:
        cat = await self.get(catalog_id, company_id, namespace)
        if cat is None:
            raise ValueError("Каталог не найден")
        if cat.is_public:
            raise ValueError("Публичный каталог доступен всей компании в этом пространстве")
        if cat.owner_user_id == user_id:
            raise ValueError("Владелец уже имеет полный доступ к каталогу")
        async with self._db.session() as session:
            existing = await session.execute(
                select(OfficeCatalogMember).where(
                    OfficeCatalogMember.catalog_id == catalog_id,
                    OfficeCatalogMember.user_id == user_id,
                )
            )
            found = existing.scalar_one_or_none()
            if found is not None:
                return found
            row = OfficeCatalogMember(
                catalog_id=catalog_id,
                user_id=user_id,
                created_at=datetime.now(timezone.utc),
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

    async def remove_member(self, catalog_id: str, user_id: str) -> bool:
        async with self._db.session() as session:
            result = await session.execute(
                select(OfficeCatalogMember).where(
                    OfficeCatalogMember.catalog_id == catalog_id,
                    OfficeCatalogMember.user_id == user_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True
