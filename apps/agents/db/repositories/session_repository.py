"""
Репозиторий для работы с SessionConfig.
Использует service БД, is_global=False (изолирован по компаниям).
"""

import logging
from typing import Optional, List
from datetime import datetime, timezone

from core.db.base_repository import BaseRepository
from core.db.storage import Storage
from apps.agents.models import SessionConfig, SessionStatus

logger = logging.getLogger(__name__)


class SessionRepository(BaseRepository[SessionConfig]):
    """
    Репозиторий для работы с сессиями.
    is_global=False - сессии изолированы по компаниям.
    """
    
    is_global = False

    def __init__(self, storage: Storage):
        super().__init__(storage=storage, model_class=SessionConfig)

    def _get_key(self, session_id: str) -> str:
        return f"session:{session_id}"

    def _get_prefix(self) -> str:
        return "session:"

    def _get_table_name(self) -> str:
        return "storage"

    def _extract_entity_id(self, entity: SessionConfig) -> str:
        return entity.session_id

    async def set(self, entity: SessionConfig) -> bool:
        now = datetime.now(timezone.utc)
        entity.last_activity = now
        if not entity.created_at:
            entity.created_at = now
        return await super().set(entity)

    async def find_active(
        self, platform: str, user_id: str, flow_id: str
    ) -> List[SessionConfig]:
        """
        Находит активные сессии пользователя.
        
        Args:
            platform: Платформа (telegram, web, api)
            user_id: ID пользователя
            flow_id: ID flow
            
        Returns:
            Список активных сессий
        """
        all_sessions = await self.list_all(limit=1000)
        
        active_sessions = []
        for session in all_sessions:
            if (
                session.platform == platform
                and session.user_id == user_id
                and session.flow_id == flow_id
                and session.status in [SessionStatus.ACTIVE, SessionStatus.PROCESSING]
            ):
                active_sessions.append(session)
        
        return active_sessions
