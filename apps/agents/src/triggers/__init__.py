"""
Triggers module - точки входа для запуска агентов.

Триггеры:
- telegram: Telegram Bot webhook
- cron: TaskIQ scheduler
- webhook: HTTP webhook
- email: Email polling/webhook
- redis: Redis Pub/Sub
"""

from apps.agents.src.triggers.handlers.base import (
    BaseTriggerHandler,
    TriggerRegistrationError,
    TriggerValidationError,
)
from apps.agents.src.triggers.handlers.telegram import TelegramTriggerHandler
from apps.agents.src.triggers.registry import TriggerRegistry
from apps.agents.src.triggers.executor import TriggerExecutor, OutputActionExecutor
from apps.agents.src.triggers.input_mapper import InputMapper

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
