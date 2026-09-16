"""GuestRuntime 1:1 с (flow_id, node_id), таблица storage."""

from typing import ClassVar, override

from core.db.base_repository import BaseRepository
from core.db.storage import Storage
from core.guest_runtime.models import GuestRuntime


class GuestRuntimeRepository(BaseRepository[GuestRuntime]):
    is_global: ClassVar[bool] = True
    owner_service: ClassVar[str] = "guest_runtime"

    def __init__(self, storage: Storage) -> None:
        super().__init__(storage=storage, model_class=GuestRuntime)

    @override
    def _get_key(self, entity_id: str) -> str:
        return f"guest_runtime:{entity_id}"

    @override
    def _get_prefix(self) -> str:
        return "guest_runtime:"

    @override
    def _get_table_name(self) -> str:
        return "storage"

    @override
    def _extract_entity_id(self, entity: GuestRuntime) -> str:
        return entity.guest_runtime_id

    @staticmethod
    def runtime_id(flow_id: str, node_id: str) -> str:
        return f"{flow_id}:{node_id}"
