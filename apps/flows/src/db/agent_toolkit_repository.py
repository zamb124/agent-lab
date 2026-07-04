"""Репозиторий AgentToolkit."""

from typing import ClassVar, override

from apps.flows.src.models.agent_toolkit import AgentToolkit
from core.db import BaseRepository, Storage


class AgentToolkitRepository(BaseRepository[AgentToolkit]):
    """CRUD групп инструментов HumanitecAgent."""

    is_global: ClassVar[bool] = False
    owner_service: ClassVar[str] = "flows"

    def __init__(self, storage: Storage) -> None:
        super().__init__(storage, AgentToolkit)

    @override
    def _get_key(self, entity_id: str) -> str:
        return f"agent_toolkit:{entity_id}"

    @override
    def _get_prefix(self) -> str:
        return "agent_toolkit:"

    @override
    def _get_table_name(self) -> str:
        return "agent_toolkits"

    @override
    def _extract_entity_id(self, entity: AgentToolkit) -> str:
        return entity.toolkit_id
