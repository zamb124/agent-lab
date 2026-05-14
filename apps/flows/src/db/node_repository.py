"""
Репозиторий для NodeConfig.
"""

from apps.flows.src.models import NodeConfig
from core.db import BaseRepository, Storage


class NodeRepository(BaseRepository[NodeConfig]):
    """Репозиторий для работы с нодами всех типов"""

    is_global = False
    owner_service = "flows"

    def __init__(self, storage: Storage):
        super().__init__(storage, NodeConfig)

    def _get_key(self, entity_id: str) -> str:
        return f"node:{entity_id}"

    def _get_prefix(self) -> str:
        return "node:"

    def _get_table_name(self) -> str:
        return "nodes"

    def _extract_entity_id(self, entity: NodeConfig) -> str:
        return entity.node_id
