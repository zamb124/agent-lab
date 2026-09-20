"""
TriggerConfig - конфигурация триггера для запуска агента.

Триггер = точка входа + маппинг данных в state.
Типы: telegram, cron, webhook, email, platform_event.

Триггеры хранятся в FlowConfig.triggers (не отдельная таблица).
"""

import re
from typing import ClassVar, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from core.events import assert_platform_event_type
from core.models import StrictBaseModel
from core.types import JsonObject, JsonValue

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

    model_config: ClassVar[ConfigDict] = ConfigDict(use_enum_values=False)

    trigger_id: str = Field(..., description="Уникальный ID триггера (без «.» в id)")
    name: str = Field(..., description="Название триггера")
    type: TriggerType = Field(..., description="Тип триггера")
    enabled: bool = Field(default=True, description="Активен ли триггер")

    # Специфичные настройки по типу триггера
    config: JsonObject = Field(
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
            self.post_flow_output_enabled = False
        return self


# Специфичные конфигурации по типам (для документации и валидации)

class TelegramTriggerConfig(StrictBaseModel):
    """Конфигурация Telegram триггера."""

    bot_token: str | None = Field(default=None, description="Токен бота (@var:key для секрета)")
    bot_token_resolved: str | None = Field(
        default=None,
        alias="_bot_token_resolved",
        description="Runtime-resolved bot token for unregister/deleteWebhook.",
    )
    api_base: str | None = Field(
        default=None,
        description="Override Telegram Bot API base URL for tests/local integrations.",
    )
    internal_secret_token: str | None = Field(
        default=None,
        alias="_secret_token",
        description="Runtime secret для проверки Telegram webhook header.",
    )
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
    drop_pending_updates: bool = Field(
        default=False,
        description="Передавать drop_pending_updates в Telegram setWebhook.",
    )


class TelegramUpdate(StrictBaseModel):
    """Telegram Bot API Update для поддерживаемых trigger-входов."""

    update_id: int
    message: JsonObject | None = None
    callback_query: JsonObject | None = None

    def to_payload(self) -> JsonObject:
        payload: JsonObject = {"update_id": self.update_id}
        if self.message is not None:
            payload["message"] = self.message
        if self.callback_query is not None:
            payload["callback_query"] = self.callback_query
        return payload


class TelegramGetUpdatesResponse(StrictBaseModel):
    """Ответ Telegram Bot API getUpdates."""

    ok: bool
    result: list[TelegramUpdate] | None = None
    description: str | None = None
    error_code: int | None = None


class TelegramBotApiBooleanResponse(StrictBaseModel):
    """Ответ Telegram Bot API для методов с boolean result."""

    ok: bool
    result: bool | None = None
    description: str | None = None
    error_code: int | None = None


class CronTriggerConfig(StrictBaseModel):
    """Конфигурация Cron триггера."""

    cron: str = Field(..., description="Cron выражение (0 9 * * *)")
    timezone: str = Field(default="UTC", description="Timezone")
    initial_content: str = Field(
        default="",
        description="Начальный content для state"
    )
    initial_variables: JsonObject = Field(
        default_factory=dict,
        description="Начальные переменные для state"
    )


_WEBHOOK_SECRET_HEADER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


class WebhookTriggerConfig(StrictBaseModel):
    """Конфигурация HTTP Webhook триггера."""

    secret_token: str | None = Field(
        default=None,
        description="Секретный токен для верификации"
    )
    secret_header: str = Field(
        default="X-Trigger-Secret",
        description="Имя HTTP-заголовка, из которого читается secret_token",
    )
    allowed_ips: list[str] = Field(
        default_factory=list,
        description="Whitelist IP адресов (пусто = все)"
    )

    @field_validator("secret_header")
    @classmethod
    def _validate_secret_header(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("secret_header is required")
        if not _WEBHOOK_SECRET_HEADER_RE.match(stripped):
            raise ValueError(
                "secret_header must match [A-Za-z0-9][A-Za-z0-9_-]* "
                + "(no spaces, colons, or other punctuation)"
            )
        return stripped


class EmailTriggerConfig(StrictBaseModel):
    """
    Конфигурация Email триггера на platform mail.

    Слушает входящие письма MailboxBinding (sync через mail_sync_tick).
    Фильтры опциональны: пустые = все письма ящика.
    """

    mailbox_binding_id: str = Field(
        ...,
        description="ID ящика пользователя (MailboxBinding.mailbox_binding_id)",
    )
    allowed_senders: list[str] = Field(
        default_factory=list,
        description="Substring match по from (пусто = все отправители)",
    )
    subject_contains: str = Field(
        default="",
        description="Substring match по subject (пусто = без фильтра по теме)",
    )

    @field_validator("mailbox_binding_id")
    @classmethod
    def _validate_mailbox_binding_id(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("mailbox_binding_id is required")
        return stripped


class EventFilter(StrictBaseModel):
    """Условие на payload события платформы (dot-path, без JSONPath-движка)."""

    path: str = Field(..., description="Dot-path по payload события (например entity_type)")
    op: Literal["eq", "ne", "contains"] = Field(default="eq", description="Оператор сравнения")
    value: JsonValue = Field(..., description="Ожидаемое значение")

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("EventFilter.path is required")
        return stripped


class PlatformEventTriggerConfig(StrictBaseModel):
    """Конфигурация триггера на событие платформы (шина `platform:events`)."""

    event_type: str = Field(
        ...,
        description="Тип события платформы (scope/entity/verb) из каталога core/events",
    )
    filters: list[EventFilter] = Field(
        default_factory=list,
        description="Все условия должны выполниться (AND) для запуска flow",
    )

    @field_validator("event_type")
    @classmethod
    def _validate_event_type(cls, value: str) -> str:
        return assert_platform_event_type(value.strip())


class TriggerCreateRequest(StrictBaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(use_enum_values=False)

    trigger_id: str = Field(..., description="ID триггера")
    name: str = Field(..., description="Название")
    type: TriggerType = Field(..., description="Тип триггера")
    enabled: bool = Field(default=True, description="Активен")
    config: JsonObject = Field(default_factory=dict, description="Конфигурация")
    output_mapping: dict[str, str] = Field(
        default_factory=dict,
        description="Маппинг payload -> state (state.path -> payload.path)",
    )
    input_mapping: dict[str, str] = Field(
        default_factory=dict,
        description="DEPRECATED: используйте output_mapping",
    )
    output_actions: list[OutputAction] = Field(
        default_factory=list,
        description="Действия отправки ответа в канал после агента",
    )
    post_flow_output_enabled: bool | None = Field(
        default=None,
        description="Включить рассылку после flow; None — дефолт по типу триггера",
    )
    branch_id: str = Field(
        default="default",
        description="ID ветки из FlowConfig.branches; default — entry базового flow",
    )


class TriggerCreatePayload(TriggerCreateRequest):
    flow_id: str = Field(min_length=1)


class TriggerUpdateRequest(StrictBaseModel):
    name: str | None = None
    enabled: bool | None = None
    config: JsonObject | None = None
    output_mapping: dict[str, str] | None = None
    input_mapping: dict[str, str] | None = None
    output_actions: list[OutputAction] | None = None
    post_flow_output_enabled: bool | None = None
    branch_id: str | None = None


class TriggerUpdatePayload(TriggerUpdateRequest):
    flow_id: str = Field(min_length=1)
    trigger_id: str = Field(min_length=1)


class TriggerResponse(StrictBaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(use_enum_values=False)

    trigger_id: str
    name: str
    type: TriggerType
    enabled: bool
    config: JsonObject
    output_mapping: dict[str, str]
    input_mapping: dict[str, str]
    output_actions: list[OutputAction]
    post_flow_output_enabled: bool
    branch_id: str
    webhook_url: str | None = None
    status: TriggerStatus
    last_error: str | None = None


class TriggerVerifyRequest(StrictBaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(use_enum_values=False)

    type: TriggerType = Field(..., description="Тип триггера")
    config: JsonObject = Field(default_factory=dict, description="Конфиг как в trigger.config")
    trigger_id: str | None = Field(
        default=None,
        description="Черновой ID триггера (для подсказки пути webhook)",
    )
    branch_id: str = Field(
        default="default",
        description="Ветка (branch_id) для резолва @var: (как при выполнении flow с этой веткой)",
    )


class TriggerVerifyPayload(TriggerVerifyRequest):
    flow_id: str = Field(min_length=1)


class TriggerVerifyResponse(StrictBaseModel):
    ok: bool
    metadata: JsonObject = Field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None


class TriggerFlowIdPayload(StrictBaseModel):
    flow_id: str = Field(min_length=1)
    trigger_id: str = Field(min_length=1)


class TriggerDeletedResponse(StrictBaseModel):
    status: Literal["deleted"]
    trigger_id: str


class TriggerTestRequest(StrictBaseModel):
    flow_id: str = Field(min_length=1)
    trigger_id: str = Field(min_length=1)
    payload: JsonObject = Field(default_factory=dict)


class TriggerTestResponse(StrictBaseModel):
    status: Literal["ok"]
    trigger_id: str
    trigger_type: str
    input_payload: JsonObject
    mapped_data: JsonObject


__all__ = [
    "TriggerConfig",
    "TelegramTriggerConfig",
    "TelegramUpdate",
    "TelegramGetUpdatesResponse",
    "TelegramBotApiBooleanResponse",
    "CronTriggerConfig",
    "WebhookTriggerConfig",
    "EmailTriggerConfig",
    "EventFilter",
    "PlatformEventTriggerConfig",
    "TriggerCreateRequest",
    "TriggerCreatePayload",
    "TriggerUpdateRequest",
    "TriggerUpdatePayload",
    "TriggerResponse",
    "TriggerVerifyRequest",
    "TriggerVerifyPayload",
    "TriggerVerifyResponse",
    "TriggerFlowIdPayload",
    "TriggerDeletedResponse",
    "TriggerTestRequest",
    "TriggerTestResponse",
]
