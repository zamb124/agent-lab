"""
BaseTriggerHandler - абстрактный базовый класс для обработчиков триггеров.

Каждый тип триггера (telegram, cron, webhook, email) наследует этот класс
и реализует методы register, unregister, handle.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict

from apps.flows.config import get_settings
from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.models import TriggerConfig, TriggerType
from core.logging import get_logger

logger = get_logger(__name__)


class BaseTriggerHandler(ABC):
    """
    Абстрактный базовый класс для обработчиков триггеров.

    Lifecycle:
    1. register() - вызывается при сохранении агента с новым триггером
    2. handle() - вызывается при срабатывании триггера
    3. unregister() - вызывается при удалении триггера или агента
    """

    trigger_type: TriggerType

    def __init__(self, base_url: str, *, container: FlowRuntimeContainer):
        """
        Args:
            base_url: Базовый URL сервиса для формирования webhook URL
        """
        self.base_url = base_url
        self.container = container

    @abstractmethod
    async def register(
        self,
        flow_id: str,
        trigger: TriggerConfig,
    ) -> TriggerConfig:
        """
        Регистрирует триггер.

        Выполняет специфичные действия:
        - Telegram: setWebhook API
        - Cron: schedule_by_cron в TaskIQ
        - Webhook: регистрация endpoint
        - Email: создание cron job для polling

        Args:
            flow_id: ID агента
            trigger: Конфигурация триггера

        Returns:
            Обновленный TriggerConfig с runtime данными
            (webhook_url, schedule_id, status)

        Raises:
            TriggerRegistrationError: При ошибке регистрации
        """
        pass

    @abstractmethod
    async def unregister(
        self,
        flow_id: str,
        trigger: TriggerConfig,
    ) -> None:
        """
        Снимает триггер с регистрации.

        Выполняет специфичные действия:
        - Telegram: deleteWebhook API
        - Cron: удаление schedule из Redis
        - Webhook: удаление endpoint
        - Email: удаление cron job

        Args:
            flow_id: ID агента
            trigger: Конфигурация триггера
        """
        pass

    @abstractmethod
    async def handle(
        self,
        flow_id: str,
        trigger_id: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Обрабатывает входящее событие триггера.

        1. Валидирует payload (secret_token, allowed_users, etc.)
        2. Применяет input_mapping для формирования initial state
        3. Запускает агента через TriggerExecutor

        Args:
            flow_id: ID агента
            trigger_id: ID триггера
            payload: Входящие данные (Telegram Update, webhook body, etc.)

        Returns:
            Результат выполнения агента
        """
        pass

    def generate_webhook_url(self, flow_id: str, trigger_id: str) -> str:
        """
        Генерирует URL для webhook.

        Args:
            flow_id: ID агента
            trigger_id: ID триггера

        Returns:
            Полный URL webhook
        """
        trigger_type = self.trigger_type.value
        svc = get_settings().server.name
        return f"{self.base_url}/{svc}/api/v1/triggers/{trigger_type}/{flow_id}/{trigger_id}"

    def _log_register(self, flow_id: str, trigger_id: str) -> None:
        """Логирует регистрацию триггера."""
        logger.info(
            f"Registering {self.trigger_type.value} trigger: "
            f"flow_id={flow_id}, trigger={trigger_id}"
        )

    def _log_unregister(self, flow_id: str, trigger_id: str) -> None:
        """Логирует снятие триггера."""
        logger.info(
            f"Unregistering {self.trigger_type.value} trigger: "
            f"flow_id={flow_id}, trigger={trigger_id}"
        )


class TriggerRegistrationError(Exception):
    """Ошибка регистрации триггера."""

    def __init__(self, trigger_type: str, flow_id: str, trigger_id: str, message: str):
        self.trigger_type = trigger_type
        self.flow_id = flow_id
        self.trigger_id = trigger_id
        super().__init__(
            f"Failed to register {trigger_type} trigger "
            f"(flow_id={flow_id}, trigger={trigger_id}): {message}"
        )


class TriggerValidationError(Exception):
    """Ошибка валидации входящего запроса триггера."""

    def __init__(self, message: str):
        super().__init__(message)


__all__ = [
    "BaseTriggerHandler",
    "TriggerRegistrationError",
    "TriggerValidationError",
]
