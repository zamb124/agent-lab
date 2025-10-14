"""
Репозиторий для работы с SessionConfig.
"""

import logging
import json
from typing import Optional, List
from datetime import datetime, timezone

from sqlalchemy import select

from app.db.repositories.base import BaseRepository
from app.db.repositories.storage import Storage
from app.models import SessionConfig, SessionStatus
from app.db.database import AsyncSessionLocal
from app.db.models import Storage as StorageModel

logger = logging.getLogger(__name__)


class SessionRepository(BaseRepository[SessionConfig]):
    """Репозиторий для работы с сессиями"""

    def _get_key(self, session_id: str) -> str:
        """Формирует ключ session:session_id"""
        return f"session:{session_id}"

    def _get_prefix(self) -> str:
        """Префикс для поиска сессий"""
        return "session:"

    async def get(self, session_id: str) -> Optional[SessionConfig]:
        """
        Получает сессию по ID.
        
        Args:
            session_id: Идентификатор сессии
            
        Returns:
            SessionConfig или None если не найдена
        """
        key = self._get_key(session_id)
        data = await self.storage.get(key)
        if data:
            try:
                return SessionConfig.model_validate_json(data)
            except Exception as e:
                logger.error(f"Ошибка парсинга сессии {session_id}: {e}")
                return None
        return None

    async def set(self, config: SessionConfig) -> bool:
        """
        Сохраняет конфигурацию сессии.
        
        Args:
            config: Конфигурация сессии
            
        Returns:
            True если сохранение успешно
        """
        now = datetime.now(timezone.utc)
        config.last_activity = now
        if not config.created_at:
            config.created_at = now

        key = self._get_key(config.session_id)
        data = config.model_dump_json()
        return await self.storage.set(key, data)

    async def delete(self, session_id: str) -> bool:
        """
        Удаляет сессию по ID.
        
        Args:
            session_id: Идентификатор сессии
            
        Returns:
            True если удаление успешно
        """
        key = self._get_key(session_id)
        return await self.storage.delete(key)

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
        prefix = self._get_prefix()
        keys = await self.storage.list_by_prefix(prefix)

        sessions = []
        for key in keys:
            session_json = await self.storage.get(key)
            if not session_json:
                continue
                
            data = json.loads(session_json)
            
            if not isinstance(data, dict):
                continue
            if not all(field in data for field in ['session_id', 'platform', 'user_id']):
                logger.debug(f"Ключ {key} не содержит обязательные поля SessionConfig, пропускаем")
                continue
                
            session = SessionConfig.model_validate_json(session_json)
            if (
                session.platform == platform
                and session.user_id == user_id
                and session.flow_id == flow_id
                and session.status in [SessionStatus.ACTIVE, SessionStatus.PROCESSING]
            ):
                sessions.append(session)

        return sessions

    async def list_all(self, limit: int = 100) -> List[SessionConfig]:
        """
        Возвращает список всех сессий.
        
        Args:
            limit: Максимальное количество результатов
            
        Returns:
            Список конфигураций сессий
        """
        prefix = self._get_prefix()
        keys = await self.storage.list_by_prefix(prefix, limit=limit)
        
        sessions = []
        for key in keys:
            data = await self.storage.get(key)
            if data:
                try:
                    session = SessionConfig.model_validate_json(data)
                    sessions.append(session)
                except Exception as e:
                    logger.error(f"Ошибка парсинга сессии {key}: {e}")
                    continue
        
        return sessions

