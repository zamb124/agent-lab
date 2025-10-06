"""
Простая фабрика для создания Flow экземпляров.
"""

import logging

from app.core.storage import Storage
from app.flows.flow import Flow

logger = logging.getLogger(__name__)


class FlowFactory:
    """Простая фабрика для Flow"""

    def __init__(self):
        self.storage = Storage()

    async def get_flow(self, flow_id: str) -> Flow:
        """
        Получает Flow по ID из БД и создает экземпляр.

        Args:
            flow_id: Идентификатор flow

        Returns:
            Экземпляр Flow
        """
        # Загружаем конфигурацию из БД
        config = await self.storage.get_flow_config(flow_id)
        if not config:
            raise ValueError(f"Flow {flow_id} не найден в БД")

        # Создаем экземпляр Flow
        flow = Flow(config)
        await flow.initialize()

        logger.debug(f"Flow {flow_id} создан")
        return flow
