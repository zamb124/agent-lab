"""PostgreSQL repository for revocable same-context Flow UI grants."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import final

from sqlalchemy import desc, select, update

from apps.flows.src.db.models import FlowUIShareGrants, utc_now
from core.db.storage import Storage
from core.models.flow_ui_share import FlowUIShareGrant


def _grant(row: FlowUIShareGrants) -> FlowUIShareGrant:
    return FlowUIShareGrant.model_validate(
        {
            "grant_id": row.grant_id,
            "company_id": row.company_id,
            "flow_id": row.flow_id,
            "branch_id": row.branch_id,
            "context_id": row.context_id,
            "document_id": row.document_id,
            "minimum_revision": int(row.minimum_revision),
            "permission": row.permission,
            "redacted_value_paths": list(row.redacted_value_paths),
            "created_by_user_id": row.created_by_user_id,
            "expires_at": row.expires_at,
            "revoked_at": row.revoked_at,
            "created_at": row.created_at,
        }
    )


@final
class FlowUIShareRepository:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    async def create(self, grant: FlowUIShareGrant) -> FlowUIShareGrant:
        async with self._storage.get_session() as session:
            async with session.begin():
                row = FlowUIShareGrants(**grant.model_dump(mode="python"))
                session.add(row)
        return grant

    async def get(self, grant_id: str) -> FlowUIShareGrant | None:
        async with self._storage.get_session() as session:
            row = await session.get(FlowUIShareGrants, grant_id)
            return None if row is None else _grant(row)

    async def get_active(self, grant_id: str) -> FlowUIShareGrant | None:
        now = datetime.now(UTC)
        async with self._storage.get_session() as session:
            result = await session.execute(
                select(FlowUIShareGrants).where(
                    FlowUIShareGrants.grant_id == grant_id,
                    FlowUIShareGrants.revoked_at.is_(None),
                    FlowUIShareGrants.expires_at > now,
                )
            )
            row = result.scalar_one_or_none()
            return None if row is None else _grant(row)

    async def list_for_owner(
        self,
        *,
        company_id: str,
        flow_id: str,
        context_id: str,
        created_by_user_id: str,
    ) -> list[FlowUIShareGrant]:
        async with self._storage.get_session() as session:
            result = await session.execute(
                select(FlowUIShareGrants)
                .where(
                    FlowUIShareGrants.company_id == company_id,
                    FlowUIShareGrants.flow_id == flow_id,
                    FlowUIShareGrants.context_id == context_id,
                    FlowUIShareGrants.created_by_user_id == created_by_user_id,
                )
                .order_by(desc(FlowUIShareGrants.created_at))
            )
            return [_grant(row) for row in result.scalars().all()]

    async def revoke(
        self,
        *,
        grant_id: str,
        company_id: str,
        created_by_user_id: str,
    ) -> bool:
        async with self._storage.get_session() as session:
            async with session.begin():
                result = await session.execute(
                    update(FlowUIShareGrants)
                    .where(
                        FlowUIShareGrants.grant_id == grant_id,
                        FlowUIShareGrants.company_id == company_id,
                        FlowUIShareGrants.created_by_user_id == created_by_user_id,
                        FlowUIShareGrants.revoked_at.is_(None),
                    )
                    .values(revoked_at=utc_now())
                    .returning(FlowUIShareGrants.grant_id)
                )
                return result.scalar_one_or_none() is not None


__all__ = ["FlowUIShareRepository"]
