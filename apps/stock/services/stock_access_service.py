"""OpenFGA-доступ к складу: Check — только AuthzService; tuples — оркестрация."""

from __future__ import annotations

from apps.stock.authz.tuples import (
    stock_warehouse_company_link,
    stock_warehouse_company_member_tuple,
    stock_warehouse_member_tuple,
    stock_warehouse_owner_tuple,
)
from core.authz.errors import AuthzDenied
from core.authz.models import AuthzObject
from core.authz.service import AuthzService
from core.authz.types import AuthzRelation
from core.websocket import raise_forbidden


class StockAccessService:
    """Проверки `stock_warehouse` и запись membership-tuples (не PDP)."""

    def __init__(self, authz: AuthzService) -> None:
        self._authz: AuthzService = authz

    @staticmethod
    def _obj(warehouse_id: str, company_id: str) -> AuthzObject:
        return AuthzObject.stock_warehouse(warehouse_id, company_id=company_id)

    async def require_view(
        self, *, company_id: str, warehouse_id: str, user_id: str
    ) -> None:
        try:
            await self._authz.require_can_view(
                self._obj(warehouse_id, company_id), user_id=user_id
            )
        except AuthzDenied as exc:
            raise_forbidden(exc)

    async def require_edit(
        self, *, company_id: str, warehouse_id: str, user_id: str
    ) -> None:
        try:
            await self._authz.require_can_edit(
                self._obj(warehouse_id, company_id), user_id=user_id
            )
        except AuthzDenied as exc:
            raise_forbidden(exc)

    async def ensure_warehouse_defaults(
        self, *, warehouse_id: str, company_id: str, owner_user_id: str
    ) -> None:
        """Склад по умолчанию открыт компании: company link + member viewer|editor."""
        await self._authz.write(
            [
                stock_warehouse_company_link(warehouse_id, company_id),
                stock_warehouse_owner_tuple(warehouse_id, company_id, owner_user_id),
                stock_warehouse_company_member_tuple(
                    warehouse_id, company_id, AuthzRelation.VIEWER
                ),
                stock_warehouse_company_member_tuple(
                    warehouse_id, company_id, AuthzRelation.EDITOR
                ),
            ]
        )

    async def grant_member(
        self,
        *,
        warehouse_id: str,
        company_id: str,
        user_id: str,
        relation: AuthzRelation,
    ) -> None:
        await self._authz.write(
            [
                stock_warehouse_member_tuple(
                    warehouse_id, company_id, user_id, relation
                )
            ]
        )

    async def revoke_member(
        self,
        *,
        warehouse_id: str,
        company_id: str,
        user_id: str,
        relation: AuthzRelation,
    ) -> None:
        await self._authz.delete(
            [
                stock_warehouse_member_tuple(
                    warehouse_id, company_id, user_id, relation
                )
            ]
        )
