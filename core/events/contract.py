"""
Контракт единой шины событий платформы.

Событие платформы — запись в Redis Stream ``platform:events``. Тип события —
строка `<scope>/<entity>/<verb>` (lowercase, snake_case, минимум 3 сегмента);
контракт имён совпадает с фронтенд-реестром
`core/frontend/static/lib/events/contract.js`.

Одно событие обслуживает два класса потребителей:

- **UI-доставка** (частный случай): события с непустым ``delivery``
  форвардятся WebSocket-менеджером в сокеты адресата. В WS-фрейм уходит
  событие без поля ``delivery``:

      {
          "event_id": "...",
          "type": "<scope>/<entity>/<verb>",
          "company_id": "...",
          "payload": <JSON>,
          "meta": { "ts": ..., "source": ..., "trace_id": ..., ... }
      }

- **Durable-потребители**: consumer groups (XREADGROUP) читают все события
  at-least-once; ``delivery`` для них — просто метаданные адресации UI.
"""

from __future__ import annotations

import re
import time
import uuid
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from core.types import JsonValue

_EVENT_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\/[a-z][a-z0-9_]*){2,}$")

PLATFORM_EVENTS_STREAM = "platform:events"

SYSTEM_COMPANY_ID = "system"
"""``company_id`` платформенных событий вне контекста конкретной компании."""


def assert_platform_event_type(event_type: str) -> str:
    """Валидировать имя события. Бросает ValueError при нарушении контракта."""
    if not event_type:
        raise ValueError(
            f"Platform event type must be non-empty string, got: {type(event_type).__name__}"
        )
    if not _EVENT_TYPE_PATTERN.match(event_type):
        message = (
            f'Platform event type "{event_type}" violates contract. '
            + "Expected scope/entity/verb (lowercase, snake_case, >= 3 segments)."
        )
        raise ValueError(message)
    return event_type


class PlatformEventMeta(BaseModel):
    """Мета-конверт события."""

    ts: int = Field(default_factory=lambda: int(time.time() * 1000), description="Epoch ms")
    source: Literal["local", "ws", "http", "router", "storage", "timer", "system"] = "system"
    actor_user_id: str | None = Field(
        default=None,
        description="user_id инициатора события (если событие вызвано действием пользователя).",
    )
    causation_id: str | None = None
    correlation_id: str | None = None
    trace_id: str | None = None
    request_id: str | None = Field(
        default=None,
        description="E2E request_id запроса-инициатора события (HTTP/WS/TaskIQ).",
    )


class EventDelivery(BaseModel):
    """
    UI-адресация события. Ровно одно из полей должно быть задано.

    - user_ids: доставка в WS-сокеты перечисленных пользователей
      (одно доменное событие — одна запись стрима, сколько бы получателей ни было).
    - company_id: рассылка всем активным сокетам компании.
    - broadcast=True: рассылка всем подключённым сокетам.
    """

    user_ids: list[str] | None = None
    company_id: str | None = None
    broadcast: bool = False

    @model_validator(mode="after")
    def _target_is_explicit(self) -> Self:
        self.assert_valid()
        return self

    def assert_valid(self) -> None:
        flags = [
            self.user_ids is not None,
            self.company_id is not None,
            bool(self.broadcast),
        ]
        if sum(flags) != 1:
            raise ValueError(
                "EventDelivery: exactly one of {user_ids, company_id, broadcast} must be set"
            )
        if self.user_ids is not None and not self.user_ids:
            raise ValueError("EventDelivery.user_ids must be non-empty when set")


class PlatformEvent(BaseModel):
    """Универсальная модель события платформы (Redis Stream `platform:events`)."""

    event_id: str = Field(default_factory=lambda: f"e_{uuid.uuid4().hex}")
    type: str = Field(description="scope/entity/verb")
    company_id: str = Field(
        default=SYSTEM_COMPANY_ID,
        description="Компания-скоуп события; system для платформенных событий.",
    )
    payload: JsonValue = Field(default=None)
    meta: PlatformEventMeta = Field(default_factory=PlatformEventMeta)
    delivery: EventDelivery | None = Field(
        default=None,
        description="UI-адресация; None — чисто доменное событие, форвардер пропускает.",
    )

    @field_validator("type")
    @classmethod
    def _validate_type(cls, v: str) -> str:
        return assert_platform_event_type(v)

    def ws_frame_json(self) -> str:
        """Сериализованный WS-фрейм для фронтенда: событие без ``delivery``."""
        return self.model_dump_json(exclude={"delivery"})


class CoreFrontendEventTypes(StrEnum):
    """Реестр core-типов frontend EventBus. Зеркалит ``CoreEvents.*`` на клиенте.

    Не типы шины ``platform:events``.
    """

    UI_TOAST_SHOW = "ui/toast/show"
    UI_TOAST_DISMISS = "ui/toast/dismiss"
    UI_MODAL_OPEN = "ui/modal/open"
    UI_MODAL_CLOSE = "ui/modal/close"
    UI_NAVIGATE = "ui/navigate/requested"

    AUTH_UNAUTHORIZED = "auth/session/unauthorized"
    AUTH_LOGGED_OUT = "auth/session/logged_out"
    AUTH_COMPANY_SWITCHED = "auth/company/switched"

    ROUTER_NAVIGATE_REQUESTED = "router/route/navigate_requested"
