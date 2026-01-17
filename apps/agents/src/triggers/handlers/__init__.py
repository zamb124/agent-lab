"""
Trigger handlers - обработчики разных типов триггеров.
"""

from apps.agents.src.triggers.handlers.base import (
    BaseTriggerHandler,
    TriggerRegistrationError,
    TriggerValidationError,
)
from apps.agents.src.triggers.handlers.telegram import TelegramTriggerHandler

__all__ = [
    "BaseTriggerHandler",
    "TelegramTriggerHandler",
    "TriggerRegistrationError",
    "TriggerValidationError",
]
