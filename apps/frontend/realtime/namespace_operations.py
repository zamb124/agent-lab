"""Команды консоли namespaces: список для админа (company_workspace + personal), lightweight create, personal."""

from __future__ import annotations

from pydantic import Field

from apps.frontend.di import Di
from core.models import StrictBaseModel
from core.models.identity_models import Namespace, NamespaceKind, User
from core.namespace import TECHNICAL_NAMESPACE_NAME_PREFIXES, personal_namespace_name
from core.pagination import OffsetPage
from core.request_scope import require_company, require_company_admin
from core.websocket import EmptyPayload, raise_conflict, raise_invalid

CONSOLE_NAMESPACE_KINDS: frozenset[NamespaceKind] = frozenset(
    {NamespaceKind.COMPANY_WORKSPACE, NamespaceKind.PERSONAL}
)


class ConsoleNamespacesListPayload(StrictBaseModel):
    limit: int = Field(default=200, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    kinds: frozenset[NamespaceKind] = Field(
        default=CONSOLE_NAMESPACE_KINDS,
        description="Технические пространства в консоли не показываются",
    )


class ConsoleNamespaceCreatePayload(StrictBaseModel):
    """Lightweight company_workspace без CRM template."""

    name: str = Field(min_length=1, max_length=100)
    description: str | None = None


async def op_namespaces_console_list(
    payload: ConsoleNamespacesListPayload, *, user: User, di: Di
) -> OffsetPage[Namespace]:
    _ = user
    _ = await require_company_admin(di.authz_service)
    kinds = frozenset(payload.kinds & CONSOLE_NAMESPACE_KINDS)
    namespaces = await di.namespace_service.list(limit=payload.limit, offset=payload.offset, kinds=kinds)
    total = await di.namespace_service.count(kinds=kinds)
    return OffsetPage[Namespace](items=namespaces, total=total, limit=payload.limit, offset=payload.offset)


async def op_namespaces_console_create(
    payload: ConsoleNamespaceCreatePayload, *, user: User, di: Di
) -> Namespace:
    _ = user
    _ = await require_company_admin(di.authz_service)
    name = payload.name.strip()
    if name == "":
        raise_invalid(ValueError("name is required"))
    if name.startswith("user-") or any(name.startswith(prefix) for prefix in TECHNICAL_NAMESPACE_NAME_PREFIXES):
        raise_invalid(ValueError("reserved namespace name prefix"))
    try:
        return await di.namespace_service.create(
            name=name, description=payload.description, kind=NamespaceKind.COMPANY_WORKSPACE
        )
    except ValueError as exc:
        raise_conflict(exc)


async def op_namespaces_personal(
    payload: EmptyPayload, *, user: User, di: Di
) -> Namespace:
    """Personal namespace текущего пользователя в активной компании (ensure)."""
    _ = payload
    _ = require_company()
    namespace = await di.namespace_service.ensure_personal_namespace(
        user.user_id, display_name=user.name
    )
    if namespace.name != personal_namespace_name(user.user_id):
        raise RuntimeError("personal namespace name mismatch")
    return namespace
