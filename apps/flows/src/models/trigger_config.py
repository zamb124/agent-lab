"""
TriggerConfig - конфигурация триггера для запуска агента.

Триггер = точка входа + маппинг данных в state.
Типы: telegram, cron, webhook, email, redis.

Триггеры хранятся в FlowConfig.triggers (не отдельная таблица).
"""

import re
from typing import Any, Dict, List, Optional

from pydantic import Field, field_validator, model_validator

from core.models import StrictBaseModel
from .enums import TriggerStatus, TriggerType
from .channel_config import OutputAction
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
    config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Конфигурация триггера (bot_token, cron, etc.)"
    )
    
    # Маппинг данных payload в state
    # Формат: {"путь_в_state": "путь_в_payload"}
    output_mapping: Dict[str, str] = Field(
        default_factory=dict,
        description="Маппинг payload path -> state path"
    )
    
    # Deprecated: используйте output_mapping
    input_mapping: Dict[str, str] = Field(
        default_factory=dict,
        description="DEPRECATED: используйте output_mapping"
    )
    
    # Output: действия после выполнения агента
    output_actions: List[OutputAction] = Field(
        default_factory=list,
        description="Действия отправки ответа в канал после выполнения агента"
    )
    post_flow_output_enabled: bool = Field(
        default=True,
        description="Выполнять output_actions после завершения flow (без interrupt)",
    )
    
    skill_id: str = Field(
        default="default",
        description="ID skill из FlowConfig.skills: какой сценарий запускать при срабатывании триггера",
    )

    # Runtime данные (заполняются при регистрации)
    webhook_url: Optional[str] = Field(
        default=None,
        description="URL webhook (генерируется при регистрации)"
    )
    schedule_id: Optional[str] = Field(
        default=None,
        description="ID в TaskIQ scheduler (для cron)"
    )
    status: TriggerStatus = Field(
        default=TriggerStatus.INACTIVE,
        description="Текущий статус триггера"
    )
    last_error: Optional[str] = Field(
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
    allowed_users: List[int] = Field(
        default_factory=list,
        description="Разрешенные user_id (пусто = все)"
    )
    allowed_chats: List[int] = Field(
        default_factory=list,
        description="Разрешенные chat_id (пусто = все)"
    )
    commands: List[str] = Field(
        default_factory=list,
        description="Реагировать только на эти команды (пусто = все сообщения)"
    )


class CronTriggerConfig(StrictBaseModel):
    """Конфигурация Cron триггера."""
    
    cron: str = Field(..., description="Cron выражение (0 9 * * *)")
    timezone: str = Field(default="UTC", description="Timezone")
    initial_content: str = Field(
        default="",
        description="Начальный content для state"
    )
    initial_variables: Dict[str, Any] = Field(
        default_factory=dict,
        description="Начальные переменные для state"
    )


class WebhookTriggerConfig(StrictBaseModel):
    """Конфигурация HTTP Webhook триггера."""
    
    secret_token: Optional[str] = Field(
        default=None,
        description="Секретный токен для верификации"
    )
    allowed_ips: List[str] = Field(
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
    imap_host: Optional[str] = Field(default=None)
    imap_port: int = Field(default=993)
    imap_user: Optional[str] = Field(default=None)
    imap_password: Optional[str] = Field(
        default=None,
        description="Пароль (@var:key для секрета)"
    )
    poll_interval_minutes: int = Field(
        default=5,
        description="Интервал проверки почты"
    )
    # Фильтры
    allowed_senders: List[str] = Field(
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
