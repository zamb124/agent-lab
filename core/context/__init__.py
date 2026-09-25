"""
Context - глобальный асинхронный контекст для запросов.
"""

from core.context.context import (
    clear_context,
    get_context,
    get_current_channel,
    require_active_company,
    require_context,
    reset_context,
    resolve_namespace_or_raise,
    set_context,
    set_current_channel,
)

__all__ = [
    "set_context",
    "get_context",
    "require_context",
    "require_active_company",
    "resolve_namespace_or_raise",
    "clear_context",
    "reset_context",
    "set_current_channel",
    "get_current_channel",
]


def __getattr__(name: str) -> object:
    """Ленивый re-export моделей: eager-импорт даёт цикл через platform_model."""
    if name == "Context":
        from core.models.context_models import Context

        return Context
    if name in {"User", "Company"}:
        from core.models.identity_models import Company, User

        return {"User": User, "Company": Company}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
