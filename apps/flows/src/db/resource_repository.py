"""
Репозиторий для ResourceDefinition.
"""

from typing import override

from apps.flows.src.models import ResourceDefinition
from core.db import BaseRepository, Storage


class ResourceRepository(BaseRepository[ResourceDefinition]):
    """Репозиторий для shared ресурсов."""

    is_global: bool = False
    owner_service: str = "flows"

    def __init__(self, storage: Storage):
        super().__init__(storage, ResourceDefinition)

    @override
    def _get_key(self, entity_id: str) -> str:
        return f"resource:{entity_id}"

    @override
    def _get_prefix(self) -> str:
        return "resource:"

    @override
    def _get_table_name(self) -> str:
        return "resources"

    @override
    def _extract_entity_id(self, entity: ResourceDefinition) -> str:
        return entity.resource_id
