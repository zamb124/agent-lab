"""
TriggerConfig - конфигурация триггера для запуска агента.

Триггер = точка входа + маппинг данных в state.
Типы: telegram, cron, webhook, email, redis.

Триггеры хранятся в FlowConfig.triggers (не отдельная таблица).
"""

import re
from typing import Any

from pydantic import Field, field_validator, model_validator

from core.models import StrictBaseModel

from .channel_config import OutputAction
from .enums import TriggerStatus, TriggerType
from .trigger_mapping_validators import validate_trigger_state_mapping_keys

_TRIGGER_ID_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")


class TriggerConfig(StrictBaseModel):
    """
    Конфигурация триггера агента.

    Payload автоматически записывается в state.triggers.{trigger_id}.
    output_mapping определяет какие данные куда положить в state.

    Пример:
    {
        "trigger_id": "tg_support",
        "name": "Telegram Support Bot",
        "type": "telegram",
        "enabled": true,
        "config": {
            "bot_token": "@var:telegram_bot_token"
        },
        "output_mapping": {
            "content": "message.text",
            "context.chat_id": "message.chat.id"
        }
    }

    Формат output_mapping: слева только content и/или context.*; variables.* запрещены.
    """

    trigger_id: str = Field(..., description="Уникальный ID триггера (без «.» в id)")
    name: str = Field(..., description="Название триггера")
    type: TriggerType = Field(..., description="Тип триггера")
    enabled: bool = Field(default=True, description="Активен ли триггер")

    # Специфичные настройки по типу триггера
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Конфигурация триггера (bot_token, cron, etc.)"
    )

    # Маппинг данных payload в state
    # Формат: {"путь_в_state": "путь_в_payload"}
    output_mapping: dict[str, str] = Field(
        default_factory=dict,
        description="Маппинг payload path -> state path"
    )

    # Deprecated: используйте output_mapping
    input_mapping: dict[str, str] = Field(
        default_factory=dict,
        description="DEPRECATED: используйте output_mapping"
    )

    # Output: действия после выполнения агента
    output_actions: list[OutputAction] = Field(
        default_factory=list,
        description="Действия отправки ответа в канал после выполнения агента"
    )
    post_flow_output_enabled: bool = Field(
        default=True,
        description="Выполнять output_actions после завершения flow (без interrupt)",
    )

    branch_id: str = Field(
        default="default",
        description="ID ветки из FlowConfig.branches: какой сценарий запускать при срабатывании триггера",
    )

    # Runtime данные (заполняются при регистрации)
    webhook_url: str | None = Field(
        default=None,
        description="URL webhook (генерируется при регистрации)"
    )
    schedule_id: str | None = Field(
        default=None,
        description="ID в TaskIQ scheduler (для cron)"
    )
    status: TriggerStatus = Field(
        default=TriggerStatus.INACTIVE,
        description="Текущий статус триггера"
    )
    last_error: str | None = Field(
        default=None,
        description="Последняя ошибка (если status=error)"
    )

    @field_validator("trigger_id")
    @classmethod
    def _validate_trigger_id(cls, v: str) -> str:
        if not v or not str(v).strip():
            msg = "trigger_id is required"
            raise ValueError(msg)
        s = str(v).strip()
        if "." in s:
            msg = "trigger_id must not contain '.' (используется в путях @state:triggers.<id>...)"
            raise ValueError(msg)
        if not _TRIGGER_ID_RE.match(s):
            msg = "trigger_id must match [a-zA-Z0-9_-]+"
            raise ValueError(msg)
        return s

    @model_validator(mode="after")
    def _after_validate(self) -> "TriggerConfig":
        validate_trigger_state_mapping_keys(self.output_mapping, "output_mapping")
        validate_trigger_state_mapping_keys(self.input_mapping, "input_mapping")
        if self.type == TriggerType.CRON and self.post_flow_output_enabled:
            object.__setattr__(self, "post_flow_output_enabled", False)
        return self


# Специфичные конфигурации по типам (для документации и валидации)

class TelegramTriggerConfig(StrictBaseModel):
    """Конфигурация Telegram триггера."""

    bot_token: str = Field(..., description="Токен бота (@var:key для секрета)")
    allowed_users: list[int] = Field(
        default_factory=list,
        description="Разрешенные user_id (пусто = все)"
    )
    allowed_chats: list[int] = Field(
        default_factory=list,
        description="Разрешенные chat_id (пусто = все)"
    )
    commands: list[str] = Field(
        default_factory=list,
        description="Реагировать только на эти команды (пусто = все сообщения)"
    )
    allowed_updates: list[str] = Field(
        default_factory=lambda: ["message"],
        description=(
            "Типы Update для setWebhook/getUpdates: message, callback_query "
            "(см. TelegramTriggerHandler.normalize_allowed_updates)"
        ),
    )


class CronTriggerConfig(StrictBaseModel):
    """Конфигурация Cron триггера."""

    cron: str = Field(..., description="Cron выражение (0 9 * * *)")
    timezone: str = Field(default="UTC", description="Timezone")
    initial_content: str = Field(
        default="",
        description="Начальный content для state"
    )
    initial_variables: dict[str, Any] = Field(
        default_factory=dict,
        description="Начальные переменные для state"
    )


class WebhookTriggerConfig(StrictBaseModel):
    """Конфигурация HTTP Webhook триггера."""

    secret_token: str | None = Field(
        default=None,
        description="Секретный токен для верификации"
    )
    allowed_ips: list[str] = Field(
        default_factory=list,
        description="Whitelist IP адресов (пусто = все)"
    )
    response_mode: str = Field(
        default="async",
        description="sync = ждать ответа, async = сразу 202"
    )


class EmailTriggerConfig(StrictBaseModel):
    """Конфигурация Email триггера."""

    provider: str = Field(
        default="imap",
        description="Провайдер: imap, mailgun, sendgrid"
    )
    # IMAP конфигурация
    imap_host: str | None = Field(default=None)
    imap_port: int = Field(default=993)
    imap_user: str | None = Field(default=None)
    imap_password: str | None = Field(
        default=None,
        description="Пароль (@var:key для секрета)"
    )
    poll_interval_minutes: int = Field(
        default=5,
        description="Интервал проверки почты"
    )
    # Фильтры
    allowed_senders: list[str] = Field(
        default_factory=list,
        description="Разрешенные отправители (пусто = все)"
    )


class RedisTriggerConfig(StrictBaseModel):
    """Конфигурация Redis Pub/Sub триггера."""

    channel: str = Field(..., description="Redis channel для подписки")
    pattern: bool = Field(
        default=False,
        description="Использовать pattern subscribe"
    )


__all__ = [
    "TriggerConfig",
    "TelegramTriggerConfig",
    "CronTriggerConfig",
    "WebhookTriggerConfig",
    "EmailTriggerConfig",
    "RedisTriggerConfig",
]
