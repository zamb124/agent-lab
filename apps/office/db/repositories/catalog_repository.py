"""
Каталоги документов и участники (ACL).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import exists, func, or_, select

from apps.office.db.base import OfficeDatabase
from apps.office.db.models import (
    OfficeCatalogMember,
    OfficeDocumentBinding,
    OfficeDocumentCatalog,
)


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
        visited: set[str] = set()
        current_id: str | None = catalog_id
        while current_id is not None:
            if current_id in visited:
                return False
            visited.add(current_id)
            cat = await self.get(current_id, company_id, namespace)
            if cat is None:
                return False
            if cat.is_public:
                return True
            if cat.owner_user_id == user_id:
                return True
            async with self._db.session() as session:
                result = await session.execute(
                    select(OfficeCatalogMember).where(
                        OfficeCatalogMember.catalog_id == current_id,
                        OfficeCatalogMember.user_id == user_id,
                    )
                )
                if result.scalar_one_or_none() is not None:
                    return True
            current_id = cat.parent_catalog_id
        return False

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
        parent_catalog_id: str | None = None,
    ) -> OfficeDocumentCatalog:
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
            is_public=is_public,
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
    ) -> OfficeDocumentCatalog:
        existing = await self.find_child_by_title(
            company_id=company_id,
            namespace=namespace,
            parent_catalog_id=parent_catalog_id,
            title=title,
        )
        if existing is not None:
            return existing
        return await self.create(
            company_id=company_id,
            namespace=namespace,
            title=title,
            owner_user_id=owner_user_id,
            parent_catalog_id=parent_catalog_id,
        )

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

    async def count_bindings(self, catalog_id: str) -> int:
        async with self._db.session() as session:
            result = await session.execute(
                select(func.count(OfficeDocumentBinding.binding_id)).where(
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
        if await self.count_bindings(catalog_id) > 0:
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
