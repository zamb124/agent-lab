"""ContextVar активной компании — leaf без импортов моделей.

``core.models.platform_model`` читает company scope только отсюда:
импорт ``core.context.context`` из базы моделей дал бы цикл
``platform_model → context → context_models → … → platform_model``.
Значение поддерживает ``context.set_context`` / ``reset_context``.
"""

import contextvars

_active_company_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "active_company_id", default=None
)


def current_active_company_id() -> str | None:
    """``company_id`` активной компании текущего контекста или ``None``."""
    return _active_company_id.get()


def set_active_company_id(company_id: str | None) -> None:
    """Вызывается только ``core.context.context`` при смене контекста."""
    _ = _active_company_id.set(company_id)
