"""
Репозиторий для работы с AgentConfig.
Использует service БД, is_global=False (изолирован по компаниям).
"""

import logging
from datetime import datetime, timezone

from core.db.base_repository import BaseRepository
from core.db.storage import Storage
from apps.agents.models import AgentConfig

logger = logging.getLogger(__name__)


class AgentRepository(BaseRepository[AgentConfig]):
    """
    Репозиторий для работы с конфигурациями агентов.
    is_global=False - агенты изолированы по компаниям.
    owner_service=agents - принадлежит сервису agents.
    """
    
    is_global = False
    owner_service = "agents"
    api_prefix = "agent"
    
    @classmethod
    def get_service_url(cls) -> str:
        """URL сервиса agents"""
        from apps.agents.db.repositories import get_agents_service_url
        return get_agents_service_url()

    def __init__(self, storage: Storage):
        super().__init__(storage=storage, model_class=AgentConfig)

    def _get_key(self, agent_id: str) -> str:
        return f"agent:{agent_id}"

    def _get_prefix(self) -> str:
        return "agent:"

    def _get_table_name(self) -> str:
        return "storage"

    def _extract_entity_id(self, entity: AgentConfig) -> str:
        return entity.agent_id

    async def set(self, entity: AgentConfig) -> bool:
        now = datetime.now(timezone.utc)
        entity.updated_at = now
        if not entity.created_at:
            entity.created_at = now
        return await super().set(entity)
