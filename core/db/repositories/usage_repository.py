"""
Репозиторий для работы с UsageRecord.
Использует shared БД, is_global=False (изолирован по компаниям).
Хранит данные в отдельной таблице usage.
"""

from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import DateTime, cast, select

from core.db.base_repository import BaseRepository
from core.db.storage import Storage
from core.logging import get_logger
from core.models.billing_models import UsageRecord
from core.tracing.repository import ADMIN_FACETS_MAX_LIMIT, _admin_ilike, _facet_query_fragment

logger = get_logger(__name__)
ADMIN_USAGE_MAX_LIMIT = 5000

class UsageRepository(BaseRepository[UsageRecord]):
    """
    Репозиторий для работы с записями использования.
    is_global=False - записи изолированы по компаниям.
    Хранит данные в таблице usage в shared_db.
    """

    is_global = False

    def __init__(self, storage: Storage):
        super().__init__(storage=storage, model_class=UsageRecord)

    def _get_key(self, usage_id: str) -> str:
        return f"usage:{usage_id}"

    def _get_key_with_resource(self, resource_name: str, usage_id: str) -> str:
        return f"usage:{resource_name}:{usage_id}"

    def _get_prefix(self) -> str:
        return "usage:"

    def _get_table_name(self) -> str:
        return "usage"

    def _extract_entity_id(self, entity: UsageRecord) -> str:
        return entity.usage_id

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
        company_id: Optional[str] = None,
        usage_type: Optional[str] = None,
        resource_name: Optional[str] = None,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> List[UsageRecord]:
        """
        Все компании: выборка из таблицы usage по полям JSON value (только админ API system).
        """
        from core.db.models.platform import Usage

        if limit < 1 or limit > ADMIN_USAGE_MAX_LIMIT:
            raise ValueError(f"limit должен быть от 1 до {ADMIN_USAGE_MAX_LIMIT}")
        if offset < 0:
            raise ValueError("offset должен быть >= 0")

        ts_expr = cast(Usage.value["timestamp"].astext, DateTime(timezone=True))
        stmt = select(Usage)
        if company_id is not None:
            stmt = stmt.where(Usage.value["company_id"].astext == company_id)
        if usage_type is not None:
            stmt = stmt.where(Usage.value["usage_type"].astext == usage_type)
        if resource_name is not None:
            stmt = stmt.where(Usage.value["resource_name"].astext == resource_name)
        if from_time is not None:
            stmt = stmt.where(ts_expr >= from_time)
        if to_time is not None:
            stmt = stmt.where(ts_expr < to_time)
        stmt = stmt.where(Usage.value["timestamp"].astext.isnot(None))
        stmt = stmt.order_by(ts_expr.desc()).offset(offset).limit(limit)

        async with self._storage.get_session() as session:
            result = await session.execute(stmt)
            rows = result.scalars().all()

        records: List[UsageRecord] = []
        for row in rows:
            raw: Any = row.value
            if not isinstance(raw, dict):
                raise ValueError(f"usage row {row.key!r}: value должен быть объектом JSON")
            records.append(UsageRecord.model_validate(raw))
        return records

    async def admin_facet_distinct_usage_types(
        self,
        *,
        q: Optional[str] = None,
        limit: int = ADMIN_FACETS_MAX_LIMIT,
    ) -> List[str]:
        from core.db.models.platform import Usage

        if limit < 1 or limit > ADMIN_FACETS_MAX_LIMIT:
            raise ValueError(f"limit должен быть от 1 до {ADMIN_FACETS_MAX_LIMIT}")
        col = Usage.value["usage_type"].astext
        frag = _facet_query_fragment(q)
        async with self._storage.get_session() as session:
            stmt = select(col).where(col.isnot(None)).where(col != "")
            if frag is not None:
                stmt = stmt.where(_admin_ilike(col, frag))
            stmt = stmt.distinct().order_by(col.asc()).limit(limit)
            result = await session.execute(stmt)
            return [row[0] for row in result.all() if row[0]]

    async def admin_facet_distinct_resource_names(
        self,
        *,
        q: Optional[str] = None,
        limit: int = ADMIN_FACETS_MAX_LIMIT,
    ) -> List[str]:
        from core.db.models.platform import Usage

        if limit < 1 or limit > ADMIN_FACETS_MAX_LIMIT:
            raise ValueError(f"limit должен быть от 1 до {ADMIN_FACETS_MAX_LIMIT}")
        col = Usage.value["resource_name"].astext
        frag = _facet_query_fragment(q)
        async with self._storage.get_session() as session:
            stmt = select(col).where(col.isnot(None)).where(col != "")
            if frag is not None:
                stmt = stmt.where(_admin_ilike(col, frag))
            stmt = stmt.distinct().order_by(col.asc()).limit(limit)
            result = await session.execute(stmt)
            return [row[0] for row in result.all() if row[0]]

