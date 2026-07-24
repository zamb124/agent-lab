"""
Trigger handlers - обработчики разных типов триггеров.
"""

from apps.flows.src.triggers.handlers.base import (
    BaseTriggerHandler,
    TriggerRegistrationError,
    TriggerValidationError,
)
from apps.flows.src.triggers.handlers.email import EmailTriggerHandler
from apps.flows.src.triggers.handlers.telegram import TelegramTriggerHandler
from apps.flows.src.triggers.handlers.webhook import WebhookTriggerHandler

__all__ = [
    "BaseTriggerHandler",
    "EmailTriggerHandler",
    "TelegramTriggerHandler",
    "TriggerRegistrationError",
    "TriggerValidationError",
    "WebhookTriggerHandler",
]
