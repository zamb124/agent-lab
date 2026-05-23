"""
SQL-репозиторий per-user OAuth credentials (shared БД, таблица integration_credentials).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from core.db.database import get_session_factory
from core.db.models.platform import IntegrationCredentialRecord
from core.db.utils import get_rowcount
from core.integrations.models import IntegrationCredential, IntegrationProvider


def _enum_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _credential_from_record(record: IntegrationCredentialRecord) -> IntegrationCredential:
    return IntegrationCredential(
        credential_id=record.credential_id,
        company_id=record.company_id,
        user_id=record.user_id,
        provider=IntegrationProvider(record.provider),
        service=record.service,
        access_token=record.access_token,
        refresh_token=record.refresh_token,
        expires_at=record.expires_at,
        scope=record.scope,
        token_type=record.token_type,
        metadata=record.metadata_json,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


class IntegrationCredentialRepository:
    def __init__(self, db_url: str) -> None:
        self._db_url = db_url

    async def get_by_user_provider_service(
        self,
        company_id: str,
        user_id: str,
        provider: IntegrationProvider,
        service: str,
    ) -> IntegrationCredential | None:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(IntegrationCredentialRecord).where(
                    IntegrationCredentialRecord.company_id == company_id,
                    IntegrationCredentialRecord.user_id == user_id,
                    IntegrationCredentialRecord.provider == _enum_value(provider),
                    IntegrationCredentialRecord.service == service,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return _credential_from_record(row)

    async def list_by_user(
        self,
        company_id: str,
        user_id: str,
    ) -> list[IntegrationCredential]:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(IntegrationCredentialRecord)
                .where(
                    IntegrationCredentialRecord.company_id == company_id,
                    IntegrationCredentialRecord.user_id == user_id,
                )
                .order_by(IntegrationCredentialRecord.created_at.asc())
            )
            rows = list(result.scalars().all())
            return [_credential_from_record(item) for item in rows]

    async def list_by_provider_service(
        self,
        provider: IntegrationProvider,
        service: str,
        *,
        limit: int = 500,
    ) -> list[IntegrationCredential]:
        """Все credentials данного провайдера+сервиса (для batch-sync задач)."""
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(IntegrationCredentialRecord)
                .where(
                    IntegrationCredentialRecord.provider == _enum_value(provider),
                    IntegrationCredentialRecord.service == service,
                )
                .order_by(IntegrationCredentialRecord.updated_at.asc())
                .limit(limit)
            )
            rows = list(result.scalars().all())
            return [_credential_from_record(item) for item in rows]

    async def upsert(self, credential: IntegrationCredential) -> None:
        session_factory = await get_session_factory(self._db_url)
        values = {
            "credential_id": credential.credential_id,
            "company_id": credential.company_id,
            "user_id": credential.user_id,
            "provider": _enum_value(credential.provider),
            "service": credential.service,
            "access_token": credential.access_token,
            "refresh_token": credential.refresh_token,
            "expires_at": credential.expires_at,
            "scope": credential.scope,
            "token_type": credential.token_type,
            "metadata_json": credential.metadata,
            "created_at": credential.created_at,
            "updated_at": credential.updated_at,
        }
        stmt = insert(IntegrationCredentialRecord).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["credential_id"],
            set_={
                "access_token": stmt.excluded.access_token,
                "refresh_token": stmt.excluded.refresh_token,
                "expires_at": stmt.excluded.expires_at,
                "scope": stmt.excluded.scope,
                "token_type": stmt.excluded.token_type,
                "metadata_json": stmt.excluded.metadata_json,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        async with session_factory() as session:
            await session.execute(stmt)
            await session.commit()

    async def delete(
        self,
        credential_id: str,
        company_id: str,
        user_id: str,
    ) -> bool:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                delete(IntegrationCredentialRecord).where(
                    IntegrationCredentialRecord.credential_id == credential_id,
                    IntegrationCredentialRecord.company_id == company_id,
                    IntegrationCredentialRecord.user_id == user_id,
                )
            )
            await session.commit()
            return get_rowcount(result) > 0

    async def delete_by_user_provider_service(
        self,
        company_id: str,
        user_id: str,
        provider: IntegrationProvider,
        service: str,
    ) -> bool:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                delete(IntegrationCredentialRecord).where(
                    IntegrationCredentialRecord.company_id == company_id,
                    IntegrationCredentialRecord.user_id == user_id,
                    IntegrationCredentialRecord.provider == _enum_value(provider),
                    IntegrationCredentialRecord.service == service,
                )
            )
            await session.commit()
            return get_rowcount(result) > 0
