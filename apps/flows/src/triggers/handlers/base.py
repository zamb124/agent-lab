"""
BaseTriggerHandler - абстрактный базовый класс для обработчиков триггеров.

Каждый тип триггера (telegram, cron, webhook, email) наследует этот класс
и реализует методы register, unregister, handle.
"""

from abc import ABC, abstractmethod

from apps.flows.config import get_settings
from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.models import TriggerConfig, TriggerType
from core.logging import get_logger
from core.types import JsonObject

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

    def __init__(self, base_url: str, *, container: FlowRuntimeContainer) -> None:
        """
        Аргументы:
            base_url: Базовый URL сервиса для формирования webhook URL
        """
        self.base_url: str = base_url
        self.container: FlowRuntimeContainer = container

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

        Аргументы:
            flow_id: ID агента
            trigger: Конфигурация триггера

        Возвращает:
            Обновленный TriggerConfig с runtime данными
            (webhook_url, schedule_id, status)

        Исключения:
            TriggerRegistrationError: При ошибке регистрации
        """
        raise NotImplementedError

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

        Аргументы:
            flow_id: ID агента
            trigger: Конфигурация триггера
        """
        raise NotImplementedError

    @abstractmethod
    async def handle(
        self,
        flow_id: str,
        trigger_id: str,
        payload: JsonObject,
    ) -> JsonObject:
        """
        Обрабатывает входящее событие триггера.

        1. Валидирует payload (secret_token, allowed_users, etc.)
        2. Применяет input_mapping для формирования initial state
        3. Запускает агента через TriggerExecutor

        Аргументы:
            flow_id: ID агента
            trigger_id: ID триггера
            payload: Входящие данные (Telegram Update, webhook body, etc.)

        Возвращает:
            Результат выполнения агента
        """
        raise NotImplementedError

    def generate_webhook_url(self, flow_id: str, trigger_id: str) -> str:
        """
        Генерирует URL для webhook.

        Аргументы:
            flow_id: ID агента
            trigger_id: ID триггера

        Возвращает:
            Полный URL webhook
        """
        trigger_type = self.trigger_type.value
        svc = get_settings().server.name
        return f"{self.base_url}/{svc}/api/v1/triggers/{trigger_type}/{flow_id}/{trigger_id}"

    def _log_register(self, flow_id: str, trigger_id: str) -> None:
        """Логирует регистрацию триггера."""
        logger.info(
            "Registering %s trigger: flow_id=%s, trigger=%s",
            self.trigger_type.value,
            flow_id,
            trigger_id,
        )

    def _log_unregister(self, flow_id: str, trigger_id: str) -> None:
        """Логирует снятие триггера."""
        logger.info(
            "Unregistering %s trigger: flow_id=%s, trigger=%s",
            self.trigger_type.value,
            flow_id,
            trigger_id,
        )


class TriggerRegistrationError(Exception):
    """Ошибка регистрации триггера."""

    def __init__(self, trigger_type: str, flow_id: str, trigger_id: str, message: str) -> None:
        self.trigger_type: str = trigger_type
        self.flow_id: str = flow_id
        self.trigger_id: str = trigger_id
        error_message = "Failed to register {} trigger (flow_id={}, trigger={}): {}".format(
            trigger_type,
            flow_id,
            trigger_id,
            message,
        )
        super().__init__(error_message)


class TriggerValidationError(Exception):
    """Ошибка валидации входящего запроса триггера."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


__all__ = [
    "BaseTriggerHandler",
    "TriggerRegistrationError",
    "TriggerValidationError",
]
