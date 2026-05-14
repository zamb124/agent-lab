"""
Репозиторий для ToolReference.
"""

from apps.flows.src.models import ToolReference
from core.db import BaseRepository, Storage


class ToolRepository(BaseRepository[ToolReference]):
    """Репозиторий для работы с инструментами"""

    is_global = False
    owner_service = "flows"

    def __init__(self, storage: Storage):
        super().__init__(storage, ToolReference)

    def _get_key(self, entity_id: str) -> str:
        return f"tool:{entity_id}"

    def _get_prefix(self) -> str:
        return "tool:"

    def _get_table_name(self) -> str:
        return "tools"

    def _extract_entity_id(self, entity: ToolReference) -> str:
        return entity.tool_id
