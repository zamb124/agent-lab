"""Ошибки домена CRM: not-found и conflict внутри `op_*` → `WsCommandError`."""


class CrmNotFoundError(LookupError):
    """Namespace, шаблон или тип не найдены."""


class CrmConflictError(RuntimeError):
    """Конфликт состояния: шаблон уже есть, тип занят сущностями."""
