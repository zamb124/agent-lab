"""
Репозиторий для работы с SessionConfig.
Наследуется от Storage, поэтому имеет все его методы + типизированную работу с SessionConfig.
"""

import logging
import json
from typing import Optional, List
from datetime import datetime, timezone

from sqlalchemy import select

from app.db.repositories.base import BaseRepository
from app.db.repositories.storage import Storage
from app.models import SessionConfig, SessionStatus
from app.db.models import Storage as StorageModel

logger = logging.getLogger(__name__)


class SessionRepository(BaseRepository[SessionConfig]):
    """
    Репозиторий для работы с сессиями.
    Наследуется от Storage, поэтому имеет все его методы (get/set/delete).
    Добавляет типизированную работу с SessionConfig через Generic[SessionConfig].
    """

    def __init__(self, storage: Storage = None):
        # Передаем model_class=SessionConfig для типизации
        super().__init__(model_class=SessionConfig, storage=storage)

    def _get_key(self, session_id: str) -> str:
        """Формирует ключ session:session_id"""
        return f"session:{session_id}"

    def _get_prefix(self) -> str:
        """Префикс для поиска сессий"""
        return "session:"

    async def get(self, session_id: str) -> Optional[SessionConfig]:
        """
        Получает сессию по ID с типизацией.

        Args:
            session_id: Идентификатор сессии

        Returns:
            SessionConfig или None если не найдена
        """
        return await self._get_typed(session_id)

    async def set(self, config: SessionConfig) -> bool:
        """
        Сохраняет конфигурацию сессии с типизацией.

        Args:
            config: Конфигурация сессии

        Returns:
            True если сохранение успешно
        """
        # Обновляем timestamp активности
        now = datetime.now(timezone.utc)
        config.last_activity = now
        if not config.created_at:
            config.created_at = now

        return await self._set_typed(config)

    async def delete(self, session_id: str) -> bool:
        """
        Удаляет сессию по ID.

        Args:
            session_id: Идентификатор сессии

        Returns:
            True если удаление успешно
        """
        return await self._delete_typed(session_id)

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

