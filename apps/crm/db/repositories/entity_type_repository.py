"""
Репозиторий для EntityType с поддержкой иерархии.

Уникальность строки: (company_id, namespace, type_id).
"""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import cast as type_cast
from typing import override

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy import update as sa_update
from sqlalchemy.orm import load_only

from apps.crm.db import entity_type_catalog_cache
from apps.crm.db.base import BaseCRMRepository
from apps.crm.db.models import EntityType
from core.db.utils import get_rowcount
from core.logging import get_logger
from core.types import JsonObject

logger = get_logger(__name__)

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

    @staticmethod
    def _keyset_after_cursor(last: EntityType):
        if last.is_system:
            return or_(
                EntityType.is_system.is_(False),
                and_(
                    EntityType.is_system.is_(True),
                    EntityType.type_id > last.type_id,
                ),
            )
        return and_(
            EntityType.is_system.is_(False),
            EntityType.type_id > last.type_id,
        )

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

    async def _fetch_all_pages(
        self,
        *,
        effective_company_id: str,
        namespace: str | None,
        include_system: bool,
        catalog_only: bool,
        page_limit: int,
    ) -> list[EntityType]:
        total = await self.count_all_for_company(namespace=namespace, company_id=effective_company_id)
        if total == 0:
            return []
        if total <= page_limit:
            return await self.list_by_company(
                include_system=include_system,
                namespace=namespace,
                company_id=effective_company_id,
                limit=total,
                offset=0,
                catalog_only=catalog_only,
            )

        items: list[EntityType] = []
        cursor: EntityType | None = None
        while True:
            async with self._db.session() as session:
                stmt = self._list_stmt(
                    effective_company_id=effective_company_id,
                    namespace=namespace,
                    include_system=include_system,
                    catalog_only=catalog_only,
                ).limit(page_limit)
                if cursor is not None:
                    stmt = stmt.where(self._keyset_after_cursor(cursor))
                result = await session.execute(stmt)
                page = list(result.scalars().all())
            if not page:
                return items
            items.extend(page)
            if len(page) < page_limit:
                return items
            cursor = page[-1]

    async def get_parent_type_id_map_for_namespace(self, namespace: str) -> dict[str, str | None]:
        """type_id -> parent_type_id в рамках одного namespace."""
        company_id = self._get_company_id()
        async with self._db.session() as session:
            stmt = select(EntityType.type_id, EntityType.parent_type_id).where(
                EntityType.company_id == company_id,
                EntityType.namespace == namespace,
            )
            result = await session.execute(stmt)
            rows = type_cast(
                list[tuple[str, str | None]],
                type_cast(object, result.all()),
            )
        return {type_id: parent_type_id for type_id, parent_type_id in rows}

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
        page_limit: int = 200,
        company_id: str | None = None,
        catalog_only: bool = True,
    ) -> list[EntityType]:
        if page_limit < 1:
            raise ValueError("page_limit must be positive")
        effective_company_id = company_id if company_id is not None else self._get_company_id()
        cached = entity_type_catalog_cache.get_cached(effective_company_id, namespace)
        if cached is not None:
            return list(cached)
        items = await self._fetch_all_pages(
            effective_company_id=effective_company_id,
            namespace=namespace,
            include_system=True,
            catalog_only=catalog_only,
            page_limit=page_limit,
        )
        entity_type_catalog_cache.put_cached(effective_company_id, namespace, items)
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
                f"EntityType {type_id!r} не найден в пространстве {source_namespace!r}"
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
        created = await super().create(entity)
        self._invalidate_catalog_cache(created.company_id)
        return created

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
            await session.commit()
            deleted = get_rowcount(result) > 0
        if deleted:
            self._invalidate_catalog_cache(effective_company_id)
        return deleted
