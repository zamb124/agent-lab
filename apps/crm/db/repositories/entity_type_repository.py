"""
Репозиторий для EntityType с поддержкой иерархии.

Уникальность строки: (company_id, namespace, type_id).
"""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import cast as type_cast
from typing import override

from sqlalchemy import delete, func, select
from sqlalchemy import update as sa_update

from apps.crm.db.base import BaseCRMRepository
from apps.crm.db.models import EntityType
from apps.crm.types import JsonObject
from core.db.utils import get_rowcount
from core.logging import get_logger

logger = get_logger(__name__)


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

    async def get_all_for_company(
        self,
        include_system: bool = True,
        namespace: str | None = None,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[EntityType]:
        company_id = self._get_company_id()
        async with self._db.session() as session:
            stmt = select(EntityType).where(EntityType.company_id == company_id)
            if namespace is not None:
                stmt = stmt.where(EntityType.namespace == namespace)
            if not include_system:
                stmt = stmt.where(EntityType.is_system.is_(False))
            stmt = (
                stmt.order_by(EntityType.is_system.desc(), EntityType.type_id.asc())
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def list_for_company_id(self, company_id: str) -> list[EntityType]:
        async with self._db.session() as session:
            stmt = select(EntityType).where(EntityType.company_id == company_id)
            result = await session.execute(stmt)
            return list(result.scalars().all())

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
    ) -> int:
        company_id = self._get_company_id()
        async with self._db.session() as session:
            stmt = (
                select(func.count())
                .select_from(EntityType)
                .where(EntityType.company_id == company_id)
            )
            if namespace is not None:
                stmt = stmt.where(EntityType.namespace == namespace)
            result = await session.execute(stmt)
            return result.scalar() or 0

    async def load_all_entity_types_for_company(
        self,
        *,
        namespace: str | None = None,
        page_limit: int = 200,
    ) -> list[EntityType]:
        if page_limit < 1:
            raise ValueError("page_limit must be positive")
        offset = 0
        items: list[EntityType] = []
        while True:
            page = await self.get_all_for_company(
                namespace=namespace,
                limit=page_limit,
                offset=offset,
            )
            if not page:
                return items
            items.extend(page)
            if len(page) < page_limit:
                return items
            offset += page_limit

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

    async def list_allowed_for_namespace(
        self,
        namespace: str,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[EntityType]:
        return await self.get_all_for_company(namespace=namespace, limit=limit, offset=offset)

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
            return get_rowcount(result) > 0
