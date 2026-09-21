"""
Репозиторий для работы с UsageRecord.
Использует shared БД, is_global=False (изолирован по компаниям).
Хранит данные в отдельной таблице usage.
"""

from datetime import datetime
from typing import ClassVar, override

from sqlalchemy import ColumnElement, DateTime, func, select
from sqlalchemy import cast as sql_cast

from core.db.base_repository import BaseRepository
from core.db.jsonb import jsonb_text
from core.db.models.platform import Usage
from core.db.storage import Storage
from core.logging import get_logger
from core.models.billing_models import UsageRecord
from core.pagination import OffsetPage
from core.tracing.repository import ADMIN_FACETS_MAX_LIMIT, admin_ilike, facet_query_fragment

logger = get_logger(__name__)
ADMIN_USAGE_MAX_LIMIT = 5000


class UsageRepository(BaseRepository[UsageRecord]):
    """
    Репозиторий для работы с записями использования.
    is_global=False - записи изолированы по компаниям.
    Хранит данные в таблице usage в shared_db.
    """

    is_global: ClassVar[bool] = False

    def __init__(self, storage: Storage):
        super().__init__(storage=storage, model_class=UsageRecord)

    @override
    def _get_key(self, usage_id: str) -> str:
        return f"usage:{usage_id}"

    def _get_key_with_resource(self, resource_name: str, usage_id: str) -> str:
        return f"usage:{resource_name}:{usage_id}"

    @override
    def _get_prefix(self) -> str:
        return "usage:"

    @override
    def _get_table_name(self) -> str:
        return "usage"

    @override
    def _extract_entity_id(self, entity: UsageRecord) -> str:
        return entity.usage_id

    @override
    async def set(self, entity: UsageRecord) -> bool:
        """Сохраняет запись с resource_name в ключе"""
        base_key = self._get_key_with_resource(entity.resource_name, entity.usage_id)
        final_key = self._build_final_key(base_key)
        table_name = self._get_table_name()

        data = entity.model_dump_json()
        return await self._storage.set_with_table(final_key, data, table_name)

    async def list_by_company(self, *, limit: int = 10000, offset: int = 0) -> list[UsageRecord]:
        """Записи использования для текущей компании."""
        return await self.list(limit=limit, offset=offset)

    async def admin_search_usage_records(
        self,
        *,
        company_id: str | None = None,
        usage_type: str | None = None,
        resource_name: str | None = None,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> OffsetPage[UsageRecord]:
        """Все компании: страница usage по полям JSON value с общим количеством (админ API system)."""
        if limit < 1 or limit > ADMIN_USAGE_MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {ADMIN_USAGE_MAX_LIMIT}")
        if offset < 0:
            raise ValueError('offset must be >= 0')

        usage_timestamp = jsonb_text(Usage.value, "timestamp")
        ts_expr = sql_cast(usage_timestamp, DateTime(timezone=True))
        filters: list[ColumnElement[bool]] = [usage_timestamp.isnot(None)]
        if company_id is not None:
            filters.append(jsonb_text(Usage.value, "company_id") == company_id)
        if usage_type is not None:
            filters.append(jsonb_text(Usage.value, "usage_type") == usage_type)
        if resource_name is not None:
            filters.append(jsonb_text(Usage.value, "resource_name") == resource_name)
        if from_time is not None:
            filters.append(ts_expr >= from_time)
        if to_time is not None:
            filters.append(ts_expr < to_time)
        page_stmt = select(Usage).where(*filters).order_by(ts_expr.desc()).offset(offset).limit(limit)
        count_stmt = select(func.count()).select_from(Usage).where(*filters)

        async with self._storage.get_session() as session:
            rows = (await session.execute(page_stmt)).scalars().all()
            total = (await session.execute(count_stmt)).scalar_one()

        return OffsetPage[UsageRecord](
            items=[UsageRecord.model_validate(row.value) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def admin_facet_distinct_usage_types(
        self,
        *,
        q: str | None = None,
        limit: int = ADMIN_FACETS_MAX_LIMIT,
    ) -> list[str]:
        if limit < 1 or limit > ADMIN_FACETS_MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {ADMIN_FACETS_MAX_LIMIT}")
        col = jsonb_text(Usage.value, "usage_type")
        frag = facet_query_fragment(q)
        async with self._storage.get_session() as session:
            stmt = select(col).where(col.isnot(None)).where(col != "")
            if frag is not None:
                stmt = stmt.where(admin_ilike(col, frag))
            stmt = stmt.distinct().order_by(col.asc()).limit(limit)
            result = await session.execute(stmt)
            return [row[0] for row in result.all() if row[0]]

    async def admin_facet_distinct_resource_names(
        self,
        *,
        q: str | None = None,
        limit: int = ADMIN_FACETS_MAX_LIMIT,
    ) -> list[str]:
        if limit < 1 or limit > ADMIN_FACETS_MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {ADMIN_FACETS_MAX_LIMIT}")
        col = jsonb_text(Usage.value, "resource_name")
        frag = facet_query_fragment(q)
        async with self._storage.get_session() as session:
            stmt = select(col).where(col.isnot(None)).where(col != "")
            if frag is not None:
                stmt = stmt.where(admin_ilike(col, frag))
            stmt = stmt.distinct().order_by(col.asc()).limit(limit)
            result = await session.execute(stmt)
            return [row[0] for row in result.all() if row[0]]
