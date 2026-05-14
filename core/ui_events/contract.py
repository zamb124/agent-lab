"""
Контракт UI-событий: Pydantic-модели и реестр платформенных типов.

Тип события — строка `<scope>/<entity>/<verb>` (lowercase, snake_case, ровно
3 сегмента). Контракт совпадает с фронтенд-реестром
`core/frontend/static/lib/events/contract.js`.

Поток сериализации в WebSocket-фрейм:
    {
        "type": "<scope>/<entity>/<verb>",
        "payload": <JSON>,
        "meta": {
            "ts": <epoch_ms>,
            "source": "ws",
            "causation_id": ...,
            "correlation_id": ...,
            "trace_id": ...
        }
    }
"""

from __future__ import annotations

import re
import time
import uuid
from enum import StrEnum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

_EVENT_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\/[a-z][a-z0-9_]*){2,}$")


def assert_ui_event_type(event_type: str) -> str:
    """Валидировать имя события. Бросает ValueError при нарушении контракта."""
    if not isinstance(event_type, str) or not event_type:
        raise ValueError(f"UI event type must be non-empty string, got: {type(event_type).__name__}")
    if not _EVENT_TYPE_PATTERN.match(event_type):
        raise ValueError(
            f'UI event type "{event_type}" violates contract. '
            "Expected scope/entity/verb (lowercase, snake_case, >= 3 segments)."
        )
    return event_type


class UIEventMeta(BaseModel):
    """Мета-конверт события."""

    ts: int = Field(default_factory=lambda: int(time.time() * 1000), description="Epoch ms")
    source: Literal["local", "ws", "http", "router", "storage", "timer", "system"] = "system"
    causation_id: Optional[str] = None
    correlation_id: Optional[str] = None
    trace_id: Optional[str] = None
    request_id: Optional[str] = Field(
        default=None,
        description="E2E request_id запроса-инициатора UI-события (HTTP/WS/TaskIQ).",
    )


class UIEvent(BaseModel):
    """Универсальная модель UI-события для канала backend→UI."""

    id: str = Field(default_factory=lambda: f"e_{uuid.uuid4().hex}")
    type: str = Field(description="scope/entity/verb")
    payload: Any = Field(default=None)
    meta: UIEventMeta = Field(default_factory=UIEventMeta)

    @field_validator("type")
    @classmethod
    def _validate_type(cls, v: str) -> str:
        return assert_ui_event_type(v)


class UIEventTarget(BaseModel):
    """
    Адресация UI-события. Ровно одно из полей должно быть задано.

    - user_id: доставка в WS-сокеты конкретного пользователя.
    - company_id: рассылка всем активным сокетам компании.
    - broadcast=True: рассылка всем подключённым сокетам.
    """

    user_id: Optional[str] = None
    company_id: Optional[str] = None
    broadcast: bool = False

    def assert_valid(self) -> None:
        flags = [
            self.user_id is not None,
            self.company_id is not None,
            bool(self.broadcast),
        ]
        if sum(flags) != 1:
            raise ValueError(
                "UIEventTarget: exactly one of {user_id, company_id, broadcast} must be set"
            )


class CoreUIEventTypes(StrEnum):
    """Реестр core-типов UI-событий. Зеркалит фронтенд-реестр CoreEvents.*"""

    UI_TOAST_SHOW = "ui/toast/show"
    UI_TOAST_DISMISS = "ui/toast/dismiss"
    UI_MODAL_OPEN = "ui/modal/open"
    UI_MODAL_CLOSE = "ui/modal/close"
    UI_NAVIGATE = "ui/navigate/requested"

    AUTH_UNAUTHORIZED = "auth/session/unauthorized"
    AUTH_LOGGED_OUT = "auth/session/logged_out"
    AUTH_COMPANY_SWITCHED = "auth/company/switched"

    ROUTER_NAVIGATE_REQUESTED = "router/route/navigate_requested"
