"""
Trigger handlers - обработчики разных типов триггеров.
"""

from apps.flows.src.triggers.handlers.base import (
    BaseTriggerHandler,
    TriggerRegistrationError,
    TriggerValidationError,
)
from apps.flows.src.triggers.handlers.telegram import TelegramTriggerHandler

__all__ = [
    "BaseTriggerHandler",
    "TelegramTriggerHandler",
    "TriggerRegistrationError",
    "TriggerValidationError",
]
