"""
Репозиторий для работы с FlowConfig.
Наследуется от Storage[FlowConfig] для работы с flows.
"""

import logging
from typing import Optional, List
from datetime import datetime, timezone

from app.db.repositories.base import BaseRepository
from app.db.repositories.storage import Storage
from app.models import FlowConfig

logger = logging.getLogger(__name__)


class FlowRepository(BaseRepository[FlowConfig]):
    """Репозиторий для работы с конфигурациями flows"""

    def __init__(self, storage: Storage = None):
        """Инициализирует репозиторий для работы с FlowConfig"""
        super().__init__(model_class=FlowConfig, storage=storage)

    def _get_key(self, flow_id: str) -> str:
        """Формирует ключ flow:flow_id"""
        return f"flow:{flow_id}"

    def _get_prefix(self) -> str:
        """Префикс для поиска flows"""
        return "flow:"

    async def get(self, flow_id: str) -> Optional[FlowConfig]:
        """
        Получает flow по ID с типизацией.

        Args:
            flow_id: Идентификатор flow

        Returns:
            FlowConfig или None если не найден
        """
        return await self._get_typed(flow_id)

    async def set(self, config: FlowConfig) -> bool:
        """
        Сохраняет конфигурацию flow с типизацией.

        Args:
            config: Конфигурация flow

        Returns:
            True если сохранение успешно
        """
        # Обновляем timestamp
        now = datetime.now(timezone.utc)
        config.updated_at = now
        if not config.created_at:
            config.created_at = now

        return await self._set_typed(config)

    async def delete(self, flow_id: str) -> bool:
        """
        Удаляет flow по ID.

        Args:
            flow_id: Идентификатор flow

        Returns:
            True если удаление успешно
        """
        return await self._delete_typed(flow_id)

    async def list_all(self, limit: int = 1000) -> List[FlowConfig]:
        """
        Возвращает список всех flows (оптимизировано - 1 запрос вместо N).

        Args:
            limit: Максимальное количество результатов

        Returns:
            Список конфигураций flows
        """
        # Оптимизация: получаем все данные за 1 запрос вместо N
        all_data = await self.get_all_by_prefix("flow:", limit=limit)

        flows = []
        for key, data in all_data.items():
            try:
                flow = FlowConfig.model_validate_json(data)
                flows.append(flow)
            except Exception as e:
                logger.error(f"Ошибка парсинга flow {key}: {e}")
                continue

        return flows

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

