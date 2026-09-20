"""Ошибки границы домена: `services/` поднимают их, `op_*` превращает в `WsCommandError`.

Один набор на платформу: сервисы не заводят свои `*NotFoundError` / `*ConflictError`.
Доменные подклассы допустимы только когда несут дополнительные атрибуты
(например, `search_index_id`).
"""


class PlatformNotFoundError(LookupError):
    """Сущность не найдена после успешной проверки доступа."""


class PlatformConflictError(RuntimeError):
    """Конфликт состояния: дубликат, занятая сущность, недопустимый переход."""


class PlatformAccessDeniedError(PermissionError):
    """Нет сессии, компании или FGA-разрешения на объект."""
