"""
Репозиторий для работы с agent_states (состояние агентов).
Использует service БД, is_global=False (изолирован по компаниям).
"""

import json
import logging
from typing import Dict, Any, Optional
from sqlalchemy import text

from core.db.base_repository import BaseRepository
from core.db.storage import Storage

logger = logging.getLogger(__name__)


class AgentStateRepository(BaseRepository[Dict[str, Any]]):
    """
    Репозиторий для работы с agent_states.
    is_global=False - состояния изолированы по компаниям.
    owner_service=agents - принадлежит сервису agents.
    """
    
    is_global = False
    owner_service = "agents"
    api_prefix = "agent_state"
    
    @classmethod
    def get_service_url(cls) -> str:
        """URL сервиса agents"""
        from apps.agents.db.repositories import get_agents_service_url
        return get_agents_service_url()

    def __init__(self, storage: Storage):
        # Используем dict как модель, так как state_data - это просто JSONB
        super().__init__(storage=storage, model_class=dict)

    def _get_key(self, session_id: str) -> str:
        return f"agent_state:{session_id}"

    def _get_prefix(self) -> str:
        return "agent_state:"

    def _get_table_name(self) -> str:
        return "agent_states"

    def _extract_entity_id(self, entity: Dict[str, Any]) -> str:
        # Для state entity - это session_id, который передается в методах
        raise NotImplementedError("AgentStateRepository не использует _extract_entity_id")

    async def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Получить состояние агента по session_id"""
        async with self._storage._get_session() as session:
            result = await session.execute(
                text("""
                    SELECT a.state_data, a.store_id
                    FROM agent_states a
                    WHERE a.session_id = :session_id
                """),
                {"session_id": session_id}
            )
            row = result.first()
            if row:
                state_data = row[0] if row[0] else {}
                store_id = row[1] if row[1] else session_id
                state_data["_store_id"] = store_id
                return state_data
            return None

    async def set(self, session_id: str, state_data: Dict[str, Any], store_id: str) -> bool:
        """Сохранить состояние агента"""
        # Убираем _store_id из state_data перед сохранением
        state_data_to_save = {k: v for k, v in state_data.items() if k != "_store_id"}
        state_data_json = json.dumps(state_data_to_save, default=str, ensure_ascii=False)
        
        async with self._storage._get_session() as session:
            async with session.begin():
                await session.execute(
                    text("""
                        INSERT INTO agent_states (session_id, store_id, state_data, updated_at)
                        VALUES (:session_id, :store_id, CAST(:state_data AS JSONB), CURRENT_TIMESTAMP)
                        ON CONFLICT (session_id)
                        DO UPDATE SET
                            store_id = :store_id,
                            state_data = CAST(:state_data AS JSONB),
                            updated_at = CURRENT_TIMESTAMP
                    """),
                    {
                        "session_id": session_id,
                        "store_id": store_id,
                        "state_data": state_data_json
                    }
                )
        return True

    async def delete(self, session_id: str) -> bool:
        """Удалить состояние агента"""
        async with self._storage._get_session() as session:
            async with session.begin():
                await session.execute(
                    text("DELETE FROM agent_states WHERE session_id = :session_id"),
                    {"session_id": session_id}
                )
        return True

