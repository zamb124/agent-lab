"""
Типы Browser Control API (§17.3 TARGET_ARCHITECTURE_RU): capabilities и ошибки.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from core.types import JsonObject


@dataclass(frozen=True)
class BrowserControlFeatures:
    """
    Матрица поддерживаемых возможностей выбранного control backend-а.

    Связи:
    - Возвращается `BrowserControlAdapter.features()`.
    - Используется API-слоем для явного capability-reporting.

    Инварианты:
    - Каждый флаг отражает фактическую поддержку, без неявных fallback-ов.

    Мотивация:
    - Позволить клиенту принимать решения по degrade-пути без проб и ошибок.

    Переиспользование:
    - Стоит: как единый capability-формат для всех адаптеров.
    """
    supports_js_injection_dom_tree: bool
    supports_cdp_dom_snapshot: bool
    supports_cdp_event_listeners: bool
    supports_ax_tree: bool
    supports_selector_map: bool


class BrowserCapabilityError(Exception):
    """
    Ошибка неподдерживаемой capability backend-а.

    Связи:
    - Бросается adapter-слоем и преобразуется в HTTP 501 в API.

    Состояние:
    - Код ошибки, сообщение и опциональные детали.

    Инварианты:
    - `to_dict()` всегда возвращает предсказуемую машиночитаемую структуру.

    Мотивация:
    - Разделить "фича не поддержана" и "непредвиденный runtime-баг".

    Переиспользование:
    - Стоит: во всех адаптерах для контролируемых ошибок поддержки capability.
    """

    code: str
    message: str
    details: JsonObject

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: JsonObject | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details if details is not None else {}

    def to_dict(self) -> JsonObject:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


class ControlPointerClickBody(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    x: float = Field(ge=0)
    y: float = Field(ge=0)
    image_width: float = Field(gt=0)
    image_height: float = Field(gt=0)
    button: Literal["left", "right", "middle"] = "left"
    click_count: int = Field(default=1, ge=1, le=3)


class ControlPointerKeyBody(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=80)


class ControlPointerTextBody(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=4096)


class ControlHumanTakeoverBody(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    owner: str = Field(default="human", min_length=1, max_length=120)


class ControlSessionStatusResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    session_id: str
    url: str
    title: str
    closed: bool = False
    human_takeover: bool = False
    human_takeover_owner: str | None = None
