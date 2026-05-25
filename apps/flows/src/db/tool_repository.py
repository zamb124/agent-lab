"""
Репозиторий для ToolReference.
"""

from typing import ClassVar, override

from apps.flows.src.models import ToolReference
from core.db import BaseRepository, Storage


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
