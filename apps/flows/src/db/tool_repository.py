"""
Репозиторий для ToolReference.
"""

from collections.abc import Collection
from typing import ClassVar, cast, override

from pydantic import ValidationError
from sqlalchemy import and_, not_, or_, select
from sqlalchemy import func as sa_func
from sqlalchemy.sql.elements import ColumnElement, Label

from apps.flows.src.db.models import Tools
from apps.flows.src.models import ToolReference
from apps.flows.src.models.enums import CodeMode
from apps.flows.src.models.tool_reference import ToolIndexMcpFilter, ToolListIndexItem
from core.db import BaseRepository, Storage
from core.db.jsonb import jsonb_text
from core.logging import get_logger
from core.types import JsonValue

logger = get_logger(__name__)


def _mcp_sql_predicate() -> ColumnElement[bool]:
    code_mode = jsonb_text(Tools.value, "code_mode")
    mcp_server_id = jsonb_text(Tools.value, "mcp_server_id")
    tool_id = jsonb_text(Tools.value, "tool_id")
    return or_(
        code_mode == CodeMode.MCP_TOOL.value,
        and_(mcp_server_id.is_not(None), mcp_server_id != ""),
        tool_id.like("mcp:%"),
    )


class ToolRepository(BaseRepository[ToolReference]):
    """Репозиторий для работы с инструментами"""

    is_global: ClassVar[bool] = False
    owner_service: ClassVar[str] = "flows"

    def __init__(self, storage: Storage) -> None:
        super().__init__(storage, ToolReference)

    @override
    def _get_key(self, entity_id: str) -> str:
        return f"tool:{entity_id}"

    @override
    def _get_prefix(self) -> str:
        return "tool:"

    @override
    def _get_table_name(self) -> str:
        return "tools"

    @override
    def _extract_entity_id(self, entity: ToolReference) -> str:
        return entity.tool_id

    _LIST_INDEX_PAGE: ClassVar[int] = 1000
    _INDEX_FIELDS: ClassVar[tuple[str, ...]] = (
        "tool_id",
        "title",
        "description",
        "tags",
        "code_mode",
        "mcp_server_id",
    )

    def _index_filters(
        self,
        *,
        mcp: ToolIndexMcpFilter,
        exclude_tool_ids: Collection[str] | None,
    ) -> list[ColumnElement[bool]]:
        prefix = self._build_final_key(self._get_prefix())
        filters: list[ColumnElement[bool]] = [Tools.key.like(f"{prefix}%")]
        mcp_pred = _mcp_sql_predicate()
        if mcp == "only":
            filters.append(mcp_pred)
        elif mcp == "exclude":
            filters.append(not_(mcp_pred))
        if exclude_tool_ids:
            filters.append(
                jsonb_text(Tools.value, "tool_id").notin_(tuple(exclude_tool_ids))
            )
        return filters

    async def list_index(
        self,
        *,
        mcp: ToolIndexMcpFilter = "all",
        exclude_tool_ids: Collection[str] | None = None,
    ) -> list[ToolListIndexItem]:
        """Tools компании: id и поля фильтра picker, без code/schema JSON."""
        filters = self._index_filters(mcp=mcp, exclude_tool_ids=exclude_tool_ids)
        value_col = Tools.value
        projected: list[Label[JsonValue] | Label[str | None]] = []
        for field_name in self._INDEX_FIELDS:
            if field_name == "tags":
                projected.append(value_col.op("->")(field_name).label(field_name))
            else:
                projected.append(jsonb_text(value_col, field_name).label(field_name))
        items: list[ToolListIndexItem] = []
        offset = 0
        async with self._storage.get_session() as session:
            while True:
                result = await session.execute(
                    select(*projected)
                    .where(*filters)
                    .order_by(Tools.updated_at.desc())
                    .offset(offset)
                    .limit(self._LIST_INDEX_PAGE)
                )
                rows = result.mappings().all()
                for row in rows:
                    payload: dict[str, JsonValue] = {}
                    for field_name in self._INDEX_FIELDS:
                        field_value = cast(JsonValue, row[field_name])
                        if field_name != "tags" and field_value is None:
                            continue
                        payload[field_name] = field_value
                    try:
                        items.append(ToolListIndexItem.model_validate(payload))
                    except ValidationError as e:
                        logger.warning("flows.failed.parse.tool.list.index", e=e)
                        continue
                if len(rows) < self._LIST_INDEX_PAGE:
                    return items
                offset += self._LIST_INDEX_PAGE

    async def count_index(
        self,
        *,
        mcp: ToolIndexMcpFilter = "all",
        exclude_tool_ids: Collection[str] | None = None,
    ) -> int:
        """Число tools компании с тем же SQL-фильтром, что list_index."""
        filters = self._index_filters(mcp=mcp, exclude_tool_ids=exclude_tool_ids)
        async with self._storage.get_session() as session:
            result = await session.execute(select(sa_func.count()).where(*filters))
            return int(result.scalar_one())
