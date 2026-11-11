"""Команды управления бейджами сотрудников — общие для консоли компании
(`frontend/badges/*_requested`) и REST-зеркала `/{svc}/api/team/badges`.

Бейдж — платформенный credential (`user_badges`); управление — обязанность
админа компании, а не складского приложения: один реестр на любые
терминалы (ТСД, POS). Check `company` admin на каждой команде.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from core.di.platform import PlatformDi
from core.errors.boundary import (
    PlatformAccessDeniedError,
    PlatformNotFoundError,
)
from core.models.base import StrictBaseModel
from core.models.identity_models import User, UserBadge
from core.pagination import OffsetPage
from core.request_scope import require_company_admin
from core.websocket import Operation


class BadgeListPayload(StrictBaseModel):
    user_id: str | None = None
    limit: int = Field(default=200, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class BadgeResponse(BaseModel):
    badge_id: str
    code: str
    user_id: str
    user_name: str
    created_at: datetime


class BadgeBindPayload(StrictBaseModel):
    user_id: str
    code: str = Field(min_length=1, max_length=128)


class BadgeUnbindPayload(StrictBaseModel):
    badge_id: str


async def _badge_response(badge: UserBadge, users: dict[str, User]) -> BadgeResponse:
    return BadgeResponse(
        badge_id=badge.badge_id,
        code=badge.code,
        user_id=badge.user_id,
        user_name=users[badge.user_id].name if badge.user_id in users else "",
        created_at=badge.created_at,
    )


async def op_badges_list(
    payload: BadgeListPayload, *, user: User, di: PlatformDi
) -> OffsetPage[BadgeResponse]:
    """Бейджи активной компании, опционально — одного сотрудника; Check `company` admin."""
    _ = user
    scope = await require_company_admin(di.authz_service)
    rows = await UserBadge.objects.filter(company_id=scope.company_id).all()
    if payload.user_id is not None:
        rows = [row for row in rows if row.user_id == payload.user_id]
    users = await User.get_many(list({row.user_id for row in rows}))
    items = [
        await _badge_response(row, users)
        for row in rows[payload.offset : payload.offset + payload.limit]
    ]
    return OffsetPage[BadgeResponse](
        items=items, total=len(rows), limit=payload.limit, offset=payload.offset
    )


async def op_badges_bind(
    payload: BadgeBindPayload, *, user: User, di: PlatformDi
) -> BadgeResponse:
    """Привязать код к сотруднику компании; Check `company` admin.

    Носитель обязан быть членом компании — иначе бейдж создаст
    «мёртвый» credential, который всегда отвечает badge_login_denied.
    """
    _ = user
    scope = await require_company_admin(di.authz_service)
    target = await User.get(payload.user_id)
    if target is None:
        raise PlatformNotFoundError(
            "User not found", error_code="badge_user_not_found"
        )
    if not target.companies.get(scope.company_id):
        raise PlatformAccessDeniedError(
            "User is not a company member", error_code="badge_user_not_member"
        )
    badge = await UserBadge.bind(
        company_id=scope.company_id, code=payload.code, user_id=payload.user_id
    )
    return await _badge_response(badge, {target.user_id: target})


async def op_badges_unbind(
    payload: BadgeUnbindPayload, *, user: User, di: PlatformDi
) -> BadgeResponse:
    """Отозвать бейдж (утерян/заменён); Check `company` admin."""
    _ = user
    scope = await require_company_admin(di.authz_service)
    badge = await UserBadge.get(payload.badge_id)
    if badge is None or badge.company_id != scope.company_id:
        raise PlatformNotFoundError(
            "Badge not found", error_code="badge_not_found"
        )
    users = await User.get_many([badge.user_id])
    _ = await UserBadge.objects.filter(badge_id=badge.badge_id).delete()
    return await _badge_response(badge, users)


BADGES_LIST_OPERATION: Operation[BadgeListPayload, PlatformDi] = Operation(
    payload_model=BadgeListPayload, fn=op_badges_list
)
BADGES_BIND_OPERATION: Operation[BadgeBindPayload, PlatformDi] = Operation(
    payload_model=BadgeBindPayload, fn=op_badges_bind
)
BADGES_UNBIND_OPERATION: Operation[BadgeUnbindPayload, PlatformDi] = Operation(
    payload_model=BadgeUnbindPayload, fn=op_badges_unbind
)
