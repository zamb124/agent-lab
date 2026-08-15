"""
Каталоги документов (data plane). ACL — только OpenFGA через OfficeAccessService.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select

from apps.office.db.base import OfficeDatabase
from apps.office.db.models import (
    OfficeDocumentBinding,
    OfficeDocumentCatalog,
)
from core.types import JsonObject


class CatalogRepository:
    def __init__(self, db: OfficeDatabase) -> None:
        self._db: OfficeDatabase = db

    async def get_or_create_default(
        self,
        *,
        company_id: str,
        namespace: str,
        owner_user_id: str,
    ) -> tuple[OfficeDocumentCatalog, bool]:
        """Возвращает (catalog, created). Caller пишет FGA при created=True."""
        if owner_user_id.strip() == "":
            raise ValueError("owner_user_id is required")
        async with self._db.session() as session:
            result = await session.execute(
                select(OfficeDocumentCatalog)
                .where(
                    OfficeDocumentCatalog.company_id == company_id,
                    OfficeDocumentCatalog.namespace == namespace,
                    OfficeDocumentCatalog.parent_catalog_id.is_(None),
                )
                .order_by(OfficeDocumentCatalog.created_at.asc())
                .limit(1)
            )
            existing = result.scalar_one_or_none()
            if existing is not None:
                return existing, False
            catalog_id = uuid.uuid4().hex
            row = OfficeDocumentCatalog(
                catalog_id=catalog_id,
                company_id=company_id,
                namespace=namespace,
                title="Общие",
                owner_user_id=owner_user_id,
                created_at=datetime.now(timezone.utc),
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row, True

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

    async def list_by_company_namespace(
        self,
        *,
        company_id: str,
        namespace: str,
    ) -> list[OfficeDocumentCatalog]:
        async with self._db.session() as session:
            result = await session.execute(
                select(OfficeDocumentCatalog)
                .where(
                    OfficeDocumentCatalog.company_id == company_id,
                    OfficeDocumentCatalog.namespace == namespace,
                )
                .order_by(OfficeDocumentCatalog.created_at.asc())
            )
            return list(result.scalars().all())

    async def create(
        self,
        *,
        company_id: str,
        namespace: str,
        title: str,
        owner_user_id: str,
        parent_catalog_id: str | None = None,
    ) -> OfficeDocumentCatalog:
        if owner_user_id.strip() == "":
            raise ValueError("owner_user_id is required")
        if parent_catalog_id is not None:
            parent = await self.get(parent_catalog_id, company_id, namespace)
            if parent is None:
                raise ValueError("Родительский каталог не найден")
        catalog_id = uuid.uuid4().hex
        row = OfficeDocumentCatalog(
            catalog_id=catalog_id,
            company_id=company_id,
            namespace=namespace,
            parent_catalog_id=parent_catalog_id,
            title=title.strip(),
            owner_user_id=owner_user_id,
            created_at=datetime.now(timezone.utc),
        )
        async with self._db.session() as session:
            session.add(row)
            await session.commit()
            await session.refresh(row)
        return row

    async def find_child_by_title(
        self,
        *,
        company_id: str,
        namespace: str,
        parent_catalog_id: str | None,
        title: str,
    ) -> OfficeDocumentCatalog | None:
        async with self._db.session() as session:
            query = select(OfficeDocumentCatalog).where(
                OfficeDocumentCatalog.company_id == company_id,
                OfficeDocumentCatalog.namespace == namespace,
                OfficeDocumentCatalog.title == title.strip(),
            )
            if parent_catalog_id is None:
                query = query.where(OfficeDocumentCatalog.parent_catalog_id.is_(None))
            else:
                query = query.where(OfficeDocumentCatalog.parent_catalog_id == parent_catalog_id)
            result = await session.execute(query.limit(1))
            return result.scalar_one_or_none()

    async def get_or_create_child_by_title(
        self,
        *,
        company_id: str,
        namespace: str,
        parent_catalog_id: str | None,
        title: str,
        owner_user_id: str,
    ) -> tuple[OfficeDocumentCatalog, bool]:
        existing = await self.find_child_by_title(
            company_id=company_id,
            namespace=namespace,
            parent_catalog_id=parent_catalog_id,
            title=title,
        )
        if existing is not None:
            return existing, False
        created = await self.create(
            company_id=company_id,
            namespace=namespace,
            title=title,
            owner_user_id=owner_user_id,
            parent_catalog_id=parent_catalog_id,
        )
        return created, True

    async def update_catalog(
        self,
        catalog_id: str,
        company_id: str,
        namespace: str,
        *,
        title: str | None = None,
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
            await session.commit()
            await session.refresh(row)
            return row

    async def list_descendant_catalog_ids(
        self,
        root_catalog_id: str,
        company_id: str,
        namespace: str,
    ) -> list[str]:
        visited: set[str] = set()
        queue: list[str] = [root_catalog_id]
        descendants: list[str] = []
        while queue:
            current_id = queue.pop(0)
            if current_id in visited:
                continue
            visited.add(current_id)
            async with self._db.session() as session:
                result = await session.execute(
                    select(OfficeDocumentCatalog.catalog_id).where(
                        OfficeDocumentCatalog.company_id == company_id,
                        OfficeDocumentCatalog.namespace == namespace,
                        OfficeDocumentCatalog.parent_catalog_id == current_id,
                    )
                )
                child_ids = list(result.scalars().all())
            for child_id in child_ids:
                if child_id in visited:
                    continue
                descendants.append(child_id)
                queue.append(child_id)
        return descendants

    async def resolve_rag_search_catalog_ids(
        self,
        root_catalog_id: str,
        company_id: str,
        namespace: str,
        *,
        include_subcatalogs: bool,
    ) -> list[str]:
        root = await self.get(root_catalog_id, company_id, namespace)
        if root is None:
            raise ValueError("Каталог не найден")
        catalog_ids: list[str] = []
        seen: set[str] = set()
        if root.rag_index_enabled:
            catalog_ids.append(root.catalog_id)
            seen.add(root.catalog_id)
        if include_subcatalogs:
            descendant_ids = await self.list_descendant_catalog_ids(
                root_catalog_id,
                company_id,
                namespace,
            )
            for descendant_id in descendant_ids:
                if descendant_id in seen:
                    continue
                descendant = await self.get(descendant_id, company_id, namespace)
                if descendant is None:
                    continue
                if descendant.rag_index_enabled:
                    catalog_ids.append(descendant.catalog_id)
                    seen.add(descendant.catalog_id)
        return catalog_ids

    async def patch_rag_index_settings(
        self,
        catalog_id: str,
        company_id: str,
        namespace: str,
        *,
        include_subcatalogs: bool | None = None,
        search_options: JsonObject | None = None,
        update_search_options: bool = False,
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
            if include_subcatalogs is not None:
                row.rag_index_include_subcatalogs = include_subcatalogs
            if update_search_options:
                row.rag_index_search_options = search_options
            await session.commit()
            await session.refresh(row)
            return row

    async def set_rag_index_include_subcatalogs(
        self,
        catalog_id: str,
        company_id: str,
        namespace: str,
        *,
        include_subcatalogs: bool,
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
            row.rag_index_include_subcatalogs = include_subcatalogs
            await session.commit()
            await session.refresh(row)
            return row

    async def set_rag_index_enabled(
        self,
        catalog_id: str,
        company_id: str,
        namespace: str,
        *,
        enabled: bool,
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
            row.rag_index_enabled = enabled
            row.rag_index_updated_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(row)
            return row

    async def count_documents(self, catalog_id: str) -> int:
        async with self._db.session() as session:
            result = await session.execute(
                select(func.count(OfficeDocumentBinding.file_id)).where(
                    OfficeDocumentBinding.catalog_id == catalog_id,
                    OfficeDocumentBinding.deleted_at.is_(None),
                )
            )
            return int(result.scalar_one())

    async def count_child_catalogs(self, catalog_id: str) -> int:
        async with self._db.session() as session:
            result = await session.execute(
                select(func.count(OfficeDocumentCatalog.catalog_id)).where(
                    OfficeDocumentCatalog.parent_catalog_id == catalog_id,
                )
            )
            return int(result.scalar_one())

    async def delete_catalog(
        self,
        catalog_id: str,
        company_id: str,
        namespace: str,
    ) -> bool:
        if await self.count_documents(catalog_id) > 0:
            raise ValueError("В каталоге есть документы")
        if await self.count_child_catalogs(catalog_id) > 0:
            raise ValueError("В каталоге есть подкаталоги")
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
