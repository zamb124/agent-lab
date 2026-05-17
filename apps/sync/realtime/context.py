from __future__ import annotations

from core.context import get_context
from core.models.identity_models import User
from core.websocket import WsCommandError


def require_current_user() -> User:
    """Вернуть пользователя из request context для REST/WS зеркал Sync."""
    context = get_context()
    if context is None:
        raise WsCommandError("forbidden", "Контекст запроса Sync не установлен.")
    return context.user


def resolve_company_id(user: User) -> str:
    """Достать company_id для Sync-команды без неявных дефолтов."""
    context = get_context()
    if context is not None and context.active_company is not None:
        return context.active_company.company_id
    if isinstance(user.active_company_id, str) and user.active_company_id:
        return user.active_company_id
    raise WsCommandError("ws_no_company", "Нет active_company_id для команды Sync.")


__all__ = ["require_current_user", "resolve_company_id"]
