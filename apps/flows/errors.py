"""Ошибки домена Flows: not-found и conflict внутри `op_*` → `WsCommandError`."""


class FlowsNotFoundError(LookupError):
    """Flow или версия не найдены."""


class FlowsConflictError(RuntimeError):
    """Конфликт состояния каталога flow."""
