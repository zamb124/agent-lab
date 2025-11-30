"""
Репозиторий для работы с FlowConfig.
Использует service БД, is_global=False (изолирован по компаниям).
"""

import logging
from typing import List
from datetime import datetime, timezone

from core.db.base_repository import BaseRepository
from core.db.storage import Storage
from apps.agents.models import FlowConfig

logger = logging.getLogger(__name__)


class FlowRepository(BaseRepository[FlowConfig]):
    """
    Репозиторий для работы с конфигурациями flows.
    is_global=False - flows изолированы по компаниям.
    owner_service=agents - принадлежит сервису agents.
    """
    
    is_global = False
    owner_service = "agents"
    api_prefix = "flow"
    
    @classmethod
    def get_service_url(cls) -> str:
        """URL сервиса agents"""
        from apps.agents.db.repositories import get_agents_service_url
        return get_agents_service_url()

    def __init__(self, storage: Storage):
        super().__init__(storage=storage, model_class=FlowConfig)

    def _get_key(self, flow_id: str) -> str:
        return f"flow:{flow_id}"

    def _get_prefix(self) -> str:
        return "flow:"

    def _get_table_name(self) -> str:
        return "storage"

    def _extract_entity_id(self, entity: FlowConfig) -> str:
        return entity.flow_id

    async def set(self, entity: FlowConfig) -> bool:
        now = datetime.now(timezone.utc)
        entity.updated_at = now
        if not entity.created_at:
            entity.created_at = now
        return await super().set(entity)

    async def find_public(self, limit: int = 100) -> List[FlowConfig]:
        """
        Находит все публичные flows.
        
        Args:
            limit: Максимальное количество результатов
            
        Returns:
            Список публичных flows
        """
        all_flows = await self.list_all(limit=limit)
        return [flow for flow in all_flows if getattr(flow, 'is_public', False)]
