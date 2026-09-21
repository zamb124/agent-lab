"""
Репозиторий для EntityType с поддержкой иерархии.

Уникальность строки: (company_id, namespace, type_id).
"""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import override

from sqlalchemy import delete, func, select
from sqlalchemy import update as sa_update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from apps.crm.db import entity_type_catalog_cache
from apps.crm.db.base import BaseCRMRepository
from apps.crm.db.models import EntityType, EntityTypeCatalogRevision
from core.db.utils import get_rowcount
from core.types import JsonObject

CATALOG_MAX_ROWS = 50_000

_CATALOG_LOAD_ONLY = (
    EntityType.type_id,
    EntityType.namespace,
    EntityType.parent_type_id,
    EntityType.name,
    EntityType.prompt,
    EntityType.required_fields,
    EntityType.optional_fields,
    EntityType.is_system,
    EntityType.extractable,
    EntityType.icon,
    EntityType.color,
    EntityType.is_event,
    EntityType.check_duplicates,
    EntityType.weight_coefficient,
    EntityType.public_fields,
    EntityType.is_context_anchor,
    EntityType.is_voice_target,
    EntityType.auto_resolve_suggests,
    EntityType.description,
    EntityType.company_id,
    EntityType.created_at,
)


class EntityTypeRepository(BaseCRMRepository[EntityType]):
    """Репозиторий для типов сущностей"""

    @property
    @override
    def model_class(self) -> type[EntityType]:
        return EntityType

    @property
    @override
    def id_field(self) -> str:
        return "type_id"

    @staticmethod
    def _invalidate_catalog_cache(company_id: str) -> None:
        entity_type_catalog_cache.invalidate_company(company_id)

    @staticmethod
    async def _read_catalog_revision(session: AsyncSession, company_id: str) -> int:
        result = await session.execute(
            select(EntityTypeCatalogRevision.revision).where(
                EntityTypeCatalogRevision.company_id == company_id
            )
        )
        value = result.scalar_one_or_none()
        if value is None:
            return 0
        return int(value)

    @staticmethod
    async def _bump_catalog_revision(session: AsyncSession, company_id: str) -> None:
        stmt = pg_insert(EntityTypeCatalogRevision).values(company_id=company_id, revision=1)
        stmt = stmt.on_conflict_do_update(
            index_elements=["company_id"],
            set_={"revision": EntityTypeCatalogRevision.revision + 1},
        )
        _ = await session.execute(stmt)

    def _list_stmt(
        self,
        *,
        effective_company_id: str,
        namespace: str | None,
        include_system: bool,
        catalog_only: bool,
    ):
        stmt = select(EntityType).where(EntityType.company_id == effective_company_id)
        if namespace is not None:
            stmt = stmt.where(EntityType.namespace == namespace)
        if not include_system:
            stmt = stmt.where(EntityType.is_system.is_(False))
        if catalog_only:
            stmt = stmt.options(load_only(*_CATALOG_LOAD_ONLY))
        return stmt.order_by(EntityType.is_system.desc(), EntityType.type_id.asc())

    async def list_by_company(
        self,
        include_system: bool = True,
        namespace: str | None = None,
        *,
        company_id: str | None = None,
        limit: int = 200,
        offset: int = 0,
        catalog_only: bool = False,
    ) -> list[EntityType]:
        effective_company_id = company_id if company_id is not None else self._get_company_id()
        async with self._db.session() as session:
            stmt = self._list_stmt(
                effective_company_id=effective_company_id,
                namespace=namespace,
                include_system=include_system,
                catalog_only=catalog_only,
            ).limit(limit).offset(offset)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_parent_type_id_map_for_namespace(self, namespace: str) -> dict[str, str | None]:
        """type_id -> parent_type_id в рамках одного namespace."""
        rows = await self.load_all_entity_types_for_company(namespace=namespace)
        return {row.type_id: row.parent_type_id for row in rows}

    async def count_all_for_company(
        self,
        namespace: str | None = None,
        *,
        company_id: str | None = None,
    ) -> int:
        effective_company_id = company_id if company_id is not None else self._get_company_id()
        async with self._db.session() as session:
            stmt = (
                select(func.count())
                .select_from(EntityType)
                .where(EntityType.company_id == effective_company_id)
            )
            if namespace is not None:
                stmt = stmt.where(EntityType.namespace == namespace)
            result = await session.execute(stmt)
            scalar = result.scalar()
            if scalar is None:
                raise RuntimeError("count_all_for_company: COUNT returned NULL")
            return int(scalar)

    async def load_all_entity_types_for_company(
        self,
        *,
        namespace: str | None = None,
        company_id: str | None = None,
        catalog_only: bool = True,
    ) -> list[EntityType]:
        effective_company_id = company_id if company_id is not None else self._get_company_id()
        async with self._db.session() as session:
            revision_before = await self._read_catalog_revision(session, effective_company_id)
            cached = entity_type_catalog_cache.get_entry(effective_company_id, namespace)
            if cached is not None and cached[0] == revision_before:
                return list(cached[1])
            stmt = self._list_stmt(
                effective_company_id=effective_company_id,
                namespace=namespace,
                include_system=True,
                catalog_only=catalog_only,
            ).limit(CATALOG_MAX_ROWS + 1)
            result = await session.execute(stmt)
            items = list(result.scalars().all())
            if len(items) > CATALOG_MAX_ROWS:
                raise RuntimeError(
                    f"EntityType catalog for company {effective_company_id!r} exceeds {CATALOG_MAX_ROWS} rows"
                )
            revision_after = await self._read_catalog_revision(session, effective_company_id)
        if revision_before == revision_after:
            entity_type_catalog_cache.put_entry(
                effective_company_id,
                namespace,
                revision_after,
                items,
            )
        return list(items)

    async def list_catalog_by_namespace(
        self,
        namespace: str,
        *,
        company_id: str | None = None,
    ) -> list[EntityType]:
        return await self.load_all_entity_types_for_company(
            namespace=namespace,
            company_id=company_id,
            catalog_only=True,
        )

    async def get_by_type_id(
        self,
        type_id: str,
        *,
        namespace: str,
        company_id: str | None = None,
    ) -> EntityType | None:
        effective_company_id = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = select(EntityType).where(
                EntityType.type_id == type_id,
                EntityType.company_id == effective_company_id,
                EntityType.namespace == namespace,
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_by_type_ids(
        self,
        type_ids: list[str],
        *,
        namespace: str,
        company_id: str | None = None,
    ) -> dict[str, EntityType]:
        """
        Batched lookup `EntityType` по списку `type_id`.

        Возвращает map `type_id -> EntityType`. Отсутствующие type_id просто
        отсутствуют в map (без raise). Раньше `suggest_service` дёргал
        `get_by_type_id` в цикле по каждому кандидату — N+1 на каждой паре.
        """
        normalized = sorted({tid.strip() for tid in type_ids if tid.strip()})
        if not normalized:
            return {}
        effective_company_id = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = select(EntityType).where(
                EntityType.type_id.in_(normalized),
                EntityType.company_id == effective_company_id,
                EntityType.namespace == namespace,
            )
            result = await session.execute(stmt)
            return {row.type_id: row for row in result.scalars().all()}

    async def list_allowed_for_namespace(
        self,
        namespace: str,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[EntityType]:
        return await self.list_by_company(namespace=namespace, limit=limit, offset=offset)

    async def update_metadata(
        self,
        type_id: str,
        *,
        namespace: str,
        company_id: str | None = None,
        **fields: object,
    ) -> None:
        await self.update_metadata_fields(
            type_id,
            namespace=namespace,
            company_id=company_id,
            fields=fields,
        )

    async def update_metadata_fields(
        self,
        type_id: str,
        *,
        namespace: str,
        company_id: str | None = None,
        fields: Mapping[str, object],
    ) -> None:
        company_id = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = (
                sa_update(EntityType)
                .where(
                    EntityType.type_id == type_id,
                    EntityType.company_id == company_id,
                    EntityType.namespace == namespace,
                )
                .values(**dict(fields))
            )
            _ = await session.execute(stmt)
            await self._bump_catalog_revision(session, company_id)
            await session.commit()
        self._invalidate_catalog_cache(company_id)

    async def merge_optional_fields_if_absent(
        self,
        type_id: str,
        *,
        namespace: str,
        company_id: str,
        extra: JsonObject,
    ) -> None:
        if not extra:
            return
        async with self._db.session() as session:
            stmt = select(EntityType).where(
                EntityType.type_id == type_id,
                EntityType.company_id == company_id,
                EntityType.namespace == namespace,
            )
            result = await session.execute(stmt)
            entity_type = result.scalar_one_or_none()
            if entity_type is None:
                raise ValueError(
                    f"EntityType '{type_id}' not found for company '{company_id}' namespace '{namespace}'"
                )
            current: JsonObject = dict(entity_type.optional_fields or {})
            for key, value in extra.items():
                if key not in current:
                    current[key] = value
            entity_type.optional_fields = current
            await self._bump_catalog_revision(session, company_id)
            await session.commit()
        self._invalidate_catalog_cache(company_id)

    async def update_color(self, type_id: str, namespace: str, color: str) -> None:
        company_id = self._get_company_id()
        async with self._db.session() as session:
            stmt = (
                sa_update(EntityType)
                .where(
                    EntityType.type_id == type_id,
                    EntityType.company_id == company_id,
                    EntityType.namespace == namespace,
                )
                .values(color=color)
            )
            _ = await session.execute(stmt)
            await self._bump_catalog_revision(session, company_id)
            await session.commit()
        self._invalidate_catalog_cache(company_id)

    async def create_custom_type(
        self,
        type_data: EntityType,
        company_id: str,
    ) -> EntityType:
        if type_data.is_system:
            raise ValueError("Cannot create system type through this method")

        type_data.company_id = company_id
        return await self.create(type_data)

    async def clone_entity_type_between_namespaces(
        self,
        type_id: str,
        *,
        source_namespace: str,
        target_namespace: str,
        company_id: str | None = None,
    ) -> EntityType:
        effective_company_id = company_id or self._get_company_id()
        src = await self.get_by_type_id(
            type_id,
            namespace=source_namespace,
            company_id=effective_company_id,
        )
        if src is None:
            raise ValueError(
                f"EntityType {type_id!r} not found in namespace {source_namespace!r}"
            )
        existing = await self.get_by_type_id(
            type_id,
            namespace=target_namespace,
            company_id=effective_company_id,
        )
        if existing is not None:
            return existing
        clone = EntityType(
            company_id=effective_company_id,
            namespace=target_namespace,
            type_id=src.type_id,
            parent_type_id=src.parent_type_id,
            name=src.name,
            description=src.description,
            prompt=src.prompt,
            required_fields=dict(src.required_fields or {}),
            optional_fields=dict(src.optional_fields or {}),
            icon=src.icon,
            color=src.color,
            is_system=src.is_system,
            is_event=src.is_event,
            check_duplicates=src.check_duplicates,
            weight_coefficient=src.weight_coefficient,
            public_fields=list(src.public_fields or []),
            is_context_anchor=src.is_context_anchor,
            extractable=src.extractable,
            is_voice_target=src.is_voice_target,
            auto_resolve_suggests=src.auto_resolve_suggests,
            created_at=datetime.now(UTC),
        )
        return await self.create(clone)

    @override
    async def create(self, entity: EntityType) -> EntityType:
        async with self._db.session() as session:
            session.add(entity)
            await self._bump_catalog_revision(session, entity.company_id)
            await session.commit()
            await session.refresh(entity)
        self._invalidate_catalog_cache(entity.company_id)
        return entity

    @override
    async def update(self, entity: EntityType) -> EntityType:
        async with self._db.session() as session:
            merged = await session.merge(entity)
            await self._bump_catalog_revision(session, merged.company_id)
            await session.commit()
            await session.refresh(merged)
        self._invalidate_catalog_cache(merged.company_id)
        return merged

    async def delete_entity_type_scoped(
        self,
        type_id: str,
        *,
        namespace: str,
        company_id: str | None = None,
    ) -> bool:
        effective_company_id = company_id or self._get_company_id()
        async with self._db.session() as session:
            stmt = delete(EntityType).where(
                EntityType.company_id == effective_company_id,
                EntityType.namespace == namespace,
                EntityType.type_id == type_id,
            )
            result = await session.execute(stmt)
            deleted = get_rowcount(result) > 0
            if deleted:
                await self._bump_catalog_revision(session, effective_company_id)
            await session.commit()
        if deleted:
            self._invalidate_catalog_cache(effective_company_id)
        return deleted
