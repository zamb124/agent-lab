"""Граница запроса: компания, пользователь и пространство. Один модуль на все сервисы."""

from __future__ import annotations

from core.authz.errors import AuthzDenied
from core.authz.service import AuthzService
from core.context import get_context, resolve_namespace_or_raise
from core.models.base import StrictBaseModel
from core.models.identity_models import ANONYMOUS_USER_ID, SYSTEM_COMPANY_ID
from core.namespace.service import NamespaceService
from core.websocket import WsCommandError, raise_forbidden


class CompanyScope(StrictBaseModel):
    company_id: str
    user_id: str


class NamespaceScope(CompanyScope):
    namespace: str


def require_company() -> CompanyScope:
    context = get_context()
    if context is None or context.active_company is None:
        raise WsCommandError("forbidden", "Компания не выбрана")
    if context.user.user_id in ("", ANONYMOUS_USER_ID):
        raise WsCommandError("forbidden", "Пользователь не авторизован")
    return CompanyScope(
        company_id=context.active_company.company_id,
        user_id=context.user.user_id,
    )


async def require_company_admin(authz_service: AuthzService) -> CompanyScope:
    """Активная компания + FGA `company#admin` для пользователя."""
    scope = require_company()
    try:
        await authz_service.require_company_admin(company_id=scope.company_id, user_id=scope.user_id)
    except AuthzDenied as exc:
        raise_forbidden(exc)
    return scope


async def require_system_admin(authz_service: AuthzService) -> CompanyScope:
    """Платформенный админ: активная компания `system` и FGA `company#admin` в ней."""
    scope = require_company()
    if scope.company_id != SYSTEM_COMPANY_ID:
        raise WsCommandError("forbidden", "Доступно только для компании system")
    return await require_company_admin(authz_service)


async def require_namespace(namespace_service: NamespaceService) -> NamespaceScope:
    company = require_company()
    try:
        raw = resolve_namespace_or_raise()
    except ValueError as exc:
        raise WsCommandError("ws_invalid_payload", str(exc)) from exc
    if raw == "default":
        _ = await namespace_service.ensure_default()
    found = await namespace_service.get(raw)
    if found is None:
        raise WsCommandError(
            "ws_invalid_payload",
            f"Пространство «{raw}» не найдено в активной компании",
        )
    if found.company_id != company.company_id:
        raise WsCommandError("forbidden", "Пространство не принадлежит активной компании")
    return NamespaceScope(
        company_id=company.company_id,
        user_id=company.user_id,
        namespace=found.name,
    )
