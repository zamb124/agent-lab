"""Общие `op_*` над реестром Namespace: один handler на все сервисы с picker'ом пространств."""

from __future__ import annotations

import asyncio

from pydantic import Field

from core.authz.errors import AuthzDenied
from core.authz.models import AuthzObject
from core.di.platform import PlatformDi
from core.models.base import StrictBaseModel
from core.models.identity_models import Namespace, NamespaceKind, NamespaceSyncSettings, User
from core.pagination import OffsetPage
from core.request_scope import require_company
from core.websocket import raise_forbidden


class NamespaceSyncSettingsUpdatePayload(StrictBaseModel):
    name: str = Field(min_length=1, description="Slug пространства")
    sync_settings: NamespaceSyncSettings | None = Field(
        default=None,
        description="Полная новая секция sync-настроек либо null для сброса к дефолту.",
    )


class NamespacesListPayload(StrictBaseModel):
    limit: int = Field(default=200, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
    kinds: frozenset[NamespaceKind] = Field(
        default=frozenset({NamespaceKind.COMPANY_WORKSPACE}),
        description="Какие виды пространств вернуть; picker'ы сервисов — только company_workspace",
    )


async def op_namespaces_list(
    payload: NamespacesListPayload,
    *,
    user: User,
    di: PlatformDi,
) -> OffsetPage[Namespace]:
    _ = user
    scope = require_company()
    try:
        await di.authz_service.require_can_view(
            AuthzObject.company(scope.company_id), user_id=scope.user_id
        )
    except AuthzDenied as exc:
        raise_forbidden(exc)
    namespaces, total = await asyncio.gather(
        di.namespace_service.list(
            limit=payload.limit, offset=payload.offset, kinds=payload.kinds
        ),
        di.namespace_service.count(kinds=payload.kinds),
    )
    return OffsetPage[Namespace](
        items=namespaces, total=total, limit=payload.limit, offset=payload.offset
    )


async def op_namespaces_sync_settings_update(
    payload: NamespaceSyncSettingsUpdatePayload,
    *,
    user: User,
    di: PlatformDi,
) -> Namespace:
    """Sync владеет только секцией `Namespace.sync_settings`; имя/описание/crm_settings — CRM."""
    _ = user
    scope = require_company()
    try:
        await di.authz_service.require_can_view(
            AuthzObject.company(scope.company_id), user_id=scope.user_id
        )
    except AuthzDenied as exc:
        raise_forbidden(exc)
    return await di.namespace_service.set_sync_settings(
        payload.name, payload.sync_settings
    )
