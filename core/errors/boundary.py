"""Ошибки границы домена: `services/` поднимают их, `op_*` превращает в `WsCommandError`.

Один набор на платформу: сервисы не заводят свои `*NotFoundError` / `*ConflictError`.
Доменные подклассы допустимы только когда несут дополнительные атрибуты
(например, `search_index_id`).
"""

from __future__ import annotations

from typing import ClassVar

from core.types import JsonObject


class PlatformBoundaryError(Exception):
    """Общие поля машинного кода для UI `platform:errors.*`."""

    _default_error_code: ClassVar[str] = ""

    def __init__(
        self,
        detail: str,
        *,
        error_code: str | None = None,
        error_params: JsonObject | None = None,
    ) -> None:
        if not detail:
            raise ValueError("PlatformBoundaryError.detail must be non-empty")
        resolved_code = error_code if error_code is not None else type(self)._default_error_code
        if not resolved_code:
            raise ValueError("PlatformBoundaryError.error_code must be non-empty")
        super().__init__(detail)
        self.detail: str = detail
        self.error_code: str = resolved_code
        self.error_params: JsonObject = error_params if error_params is not None else {}


class PlatformNotFoundError(PlatformBoundaryError):
    """Сущность не найдена после успешной проверки доступа."""

    _default_error_code: ClassVar[str] = "not_found"


class PlatformConflictError(PlatformBoundaryError):
    """Конфликт состояния: дубликат, занятая сущность, недопустимый переход."""

    _default_error_code: ClassVar[str] = "conflict"


class PlatformAccessDeniedError(PlatformBoundaryError):
    """Нет сессии, компании или FGA-разрешения на объект."""

    _default_error_code: ClassVar[str] = "forbidden"


class PlatformUnavailableError(PlatformBoundaryError):
    """Зависимая интеграция или peer не настроены/недоступны: ответ 503, не сырой 500."""

    _default_error_code: ClassVar[str] = "unavailable"
