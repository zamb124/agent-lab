"""
SQL-репозиторий API-ключей компании (shared БД, таблица api_keys).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update

from core.db.database import get_session_factory
from core.db.models.platform import ApiKeyRecord


class ApiKeyRepository:
    def __init__(self, db_url: str) -> None:
        self._db_url = db_url

    async def list_by_company(
        self,
        company_id: str,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[ApiKeyRecord]:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(ApiKeyRecord)
                .where(
                    ApiKeyRecord.company_id == company_id,
                    ApiKeyRecord.revoked.is_(False),
                )
                .order_by(ApiKeyRecord.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())

    async def get(self, key_id: str, company_id: str) -> Optional[ApiKeyRecord]:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(ApiKeyRecord).where(
                    ApiKeyRecord.key_id == key_id,
                    ApiKeyRecord.company_id == company_id,
                )
            )
            return result.scalar_one_or_none()

    async def create(self, record: ApiKeyRecord) -> None:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            session.add(record)
            await session.commit()

    async def get_by_hash(self, key_hash: str) -> Optional[ApiKeyRecord]:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(ApiKeyRecord).where(
                    ApiKeyRecord.key_hash == key_hash,
                    ApiKeyRecord.revoked.is_(False),
                )
            )
            return result.scalar_one_or_none()

    async def touch_last_used(self, key_id: str, company_id: str) -> None:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            await session.execute(
                update(ApiKeyRecord)
                .where(
                    ApiKeyRecord.key_id == key_id,
                    ApiKeyRecord.company_id == company_id,
                )
                .values(last_used=datetime.now(timezone.utc))
            )
            await session.commit()

    async def update_name(self, key_id: str, company_id: str, name: str) -> bool:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                update(ApiKeyRecord)
                .where(
                    ApiKeyRecord.key_id == key_id,
                    ApiKeyRecord.company_id == company_id,
                )
                .values(name=name)
            )
            await session.commit()
            return result.rowcount > 0

    async def revoke(self, key_id: str, company_id: str) -> bool:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                update(ApiKeyRecord)
                .where(
                    ApiKeyRecord.key_id == key_id,
                    ApiKeyRecord.company_id == company_id,
                    ApiKeyRecord.revoked.is_(False),
                )
                .values(revoked=True)
            )
            await session.commit()
            return result.rowcount > 0
