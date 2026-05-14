"""
Triggers module - точки входа для запуска агентов.

Триггеры:
- telegram: Telegram Bot webhook
- cron: TaskIQ scheduler
- webhook: HTTP webhook
- email: Email polling/webhook
- redis: Redis Pub/Sub
"""

from apps.flows.src.triggers.executor import OutputActionExecutor, TriggerExecutor
from apps.flows.src.triggers.handlers.base import (
    BaseTriggerHandler,
    TriggerRegistrationError,
    TriggerValidationError,
)
from apps.flows.src.triggers.handlers.telegram import TelegramTriggerHandler
from apps.flows.src.triggers.input_mapper import InputMapper
from apps.flows.src.triggers.registry import TriggerRegistry

__all__ = [
    "BaseTriggerHandler",
    "InputMapper",
    "OutputActionExecutor",
    "TelegramTriggerHandler",
    "TriggerExecutor",
    "TriggerRegistrationError",
    "TriggerRegistry",
    "TriggerValidationError",
]
