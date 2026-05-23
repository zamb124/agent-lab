"""
Типы Browser Control API (§17.3 TARGET_ARCHITECTURE_RU): capabilities и ошибки.
"""

from __future__ import annotations

from dataclasses import dataclass

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
