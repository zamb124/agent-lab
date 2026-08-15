"""
Репозиторий для ToolReference.
"""

from typing import ClassVar, override

from pydantic import ValidationError

from apps.flows.src.models import ToolReference
from apps.flows.src.models.tool_reference import ToolListIndexItem
from core.db import BaseRepository, Storage
from core.logging import get_logger

logger = get_logger(__name__)


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

    async def list_index(self) -> list[ToolListIndexItem]:
        """Все tools компании: id и поля фильтра picker, без code/schema JSON."""
        base_prefix = self._get_prefix()
        final_prefix = self._build_final_key(base_prefix)
        table_name = self._get_table_name()
        items: list[ToolListIndexItem] = []
        offset = 0
        while True:
            rows = await self._storage.list_json_fields_by_prefix_and_table(
                final_prefix,
                table_name,
                fields=(
                    "tool_id",
                    "title",
                    "description",
                    "tags",
                    "code_mode",
                    "mcp_server_id",
                ),
                limit=self._LIST_INDEX_PAGE,
                offset=offset,
            )
            for row in rows:
                try:
                    items.append(ToolListIndexItem.model_validate(row))
                except ValidationError as e:
                    logger.warning("Failed to parse tool list index: %s", e)
                    continue
            if len(rows) < self._LIST_INDEX_PAGE:
                return items
            offset += self._LIST_INDEX_PAGE
