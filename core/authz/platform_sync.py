"""Seed tuple: group:admin#member → platform:global#admin."""

from __future__ import annotations

from core.authz.ids import PLATFORM_ADMIN_GROUP
from core.authz.models import AuthzObject, AuthzSubject, AuthzTuple
from core.authz.service import AuthzService
from core.authz.types import AuthzRelation

__all__ = [
    "PLATFORM_ADMIN_GROUP",
    "ensure_platform_global_admin",
    "platform_admin_group_tuple",
]


def platform_admin_group_tuple() -> AuthzTuple:
    return AuthzTuple(
        subject=AuthzSubject.group_member(PLATFORM_ADMIN_GROUP),
        relation=AuthzRelation.ADMIN,
        obj=AuthzObject.platform(),
    )


async def ensure_platform_global_admin(authz: AuthzService) -> None:
    await authz.write([platform_admin_group_tuple()])
