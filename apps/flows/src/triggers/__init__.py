"""
Triggers module - точки входа для запуска агентов.

Триггеры:
- telegram: Telegram Bot webhook
- cron: TaskIQ scheduler
- webhook: HTTP webhook
- email: platform mail (MailboxBinding) via mail_sync_tick
- redis: Redis Pub/Sub
"""

from apps.flows.src.triggers.executor import TriggerExecutor
from apps.flows.src.triggers.handlers.base import (
    BaseTriggerHandler,
    TriggerRegistrationError,
    TriggerValidationError,
)
from apps.flows.src.triggers.handlers.email import EmailTriggerHandler
from apps.flows.src.triggers.handlers.telegram import TelegramTriggerHandler
from apps.flows.src.triggers.handlers.webhook import WebhookTriggerHandler
from apps.flows.src.triggers.input_mapper import InputMapper
from apps.flows.src.triggers.output_actions import OutputActionExecutor
from apps.flows.src.triggers.registry import TriggerRegistry

__all__ = [
    "BaseTriggerHandler",
    "EmailTriggerHandler",
    "InputMapper",
    "OutputActionExecutor",
    "TelegramTriggerHandler",
    "TriggerExecutor",
    "TriggerRegistrationError",
    "TriggerRegistry",
    "TriggerValidationError",
    "WebhookTriggerHandler",
]
