"""Граница запроса: компания, пользователь и пространство. Один модуль на все сервисы."""

from __future__ import annotations

import uuid

from core.authz.errors import AuthzDenied
from core.authz.models import AuthzObject
from core.authz.service import AuthzService
from core.context import get_context, resolve_namespace_or_raise
from core.context.command import current_command_event_id
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
        raise WsCommandError(
            "forbidden",
            "company_not_selected",
            error_code="company_not_selected",
        )
    if context.user.user_id in ("", ANONYMOUS_USER_ID):
        raise WsCommandError(
            "forbidden",
            "user_not_authenticated",
            error_code="user_not_authenticated",
        )
    return CompanyScope(
        company_id=context.active_company.company_id,
        user_id=context.user.user_id,
    )


def command_idempotency_key(explicit: str | None = None) -> str:
    """Ключ идемпотентности мутации леджера.

    Приоритет: явный ключ payload → ``event_id`` исполняемой WS-команды
    (повтор кадра тем же ``event_id`` — безопасный replay) → новый uuid7
    (REST/внутренний вызов без ключа, каждая попытка уникальна).
    """
    if explicit:
        return explicit
    event_id = current_command_event_id()
    if event_id:
        return event_id
    return uuid.uuid7().hex


async def require_company_viewer(authz_service: AuthzService) -> CompanyScope:
    """Активная компания + FGA `company#viewer` (участник компании)."""
    scope = require_company()
    try:
        await authz_service.require_can_view(
            AuthzObject.company(scope.company_id), user_id=scope.user_id
        )
    except AuthzDenied as exc:
        raise_forbidden(exc)
    return scope


async def require_company_admin(authz_service: AuthzService) -> CompanyScope:
    """Активная компания + FGA `company#admin` для пользователя."""
    scope = require_company()
    try:
        await authz_service.require_company_admin(company_id=scope.company_id, user_id=scope.user_id)
    except AuthzDenied as exc:
        raise_forbidden(exc)
    return scope


class CustomerScope(StrictBaseModel):
    """Покупатель витрины + компания-владелец витрины из scope его сессии."""

    customer_id: str
    phone_e164: str
    company_id: str


def require_customer() -> CustomerScope:
    """Покупатель обязателен: `Context.customer` из `customer_token` JWT.

    Сессия скопирована на компанию витрины (`scope_company_id`) — заказ
    в чужой витрине с чужим токеном не пройдёт.
    """
    context = get_context()
    if context is None or context.customer is None:
        raise WsCommandError(
            "unauthorized",
            "customer_session_required",
            error_code="session_required",
        )
    customer = context.customer
    return CustomerScope(
        customer_id=customer.customer_id,
        phone_e164=customer.phone_e164,
        company_id=customer.scope_company_id,
    )


async def require_system_admin(authz_service: AuthzService) -> CompanyScope:
    """Платформенный админ: активная компания `system` и FGA `company#admin` в ней."""
    scope = require_company()
    if scope.company_id != SYSTEM_COMPANY_ID:
        raise WsCommandError(
            "forbidden",
            "system_company_only",
            error_code="system_company_only",
        )
    return await require_company_admin(authz_service)


async def require_namespace(namespace_service: NamespaceService) -> NamespaceScope:
    company = require_company()
    try:
        raw = resolve_namespace_or_raise()
    except ValueError as exc:
        raise WsCommandError("ws_invalid_payload", str(exc), error_code="ws_invalid_payload") from exc
    if raw == "default":
        _ = await namespace_service.ensure_default()
    found = await namespace_service.get(raw)
    if found is None:
        raise WsCommandError(
            "ws_invalid_payload",
            "namespace_not_found",
            error_code="namespace_not_found",
            error_params={"namespace": raw},
        )
    if found.company_id != company.company_id:
        raise WsCommandError(
            "forbidden",
            "namespace_company_mismatch",
            error_code="namespace_company_mismatch",
        )
    return NamespaceScope(
        company_id=company.company_id,
        user_id=company.user_id,
        namespace=found.name,
    )
