"""
Репозитории shares, revisions и activity events для Documents.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import cast

from sqlalchemy import func, select

from apps.office.db.base import OfficeDatabase
from apps.office.db.models import (
    OfficeDocumentEvent,
    OfficeDocumentRevision,
    OfficeDocumentShare,
)
from core.types import JsonObject, require_json_object


class DocumentShareRepository:
    def __init__(self, db: OfficeDatabase) -> None:
        self._db: OfficeDatabase = db

    async def create(
        self,
        *,
        binding_id: str,
        company_id: str,
        created_by_user_id: str,
        permission: str,
        token_hash: str,
        expires_at: datetime | None,
    ) -> OfficeDocumentShare:
        share_id = uuid.uuid4().hex
        row = OfficeDocumentShare(
            share_id=share_id,
            binding_id=binding_id,
            company_id=company_id,
            created_by_user_id=created_by_user_id,
            permission=permission,
            token_hash=token_hash,
            expires_at=expires_at,
            created_at=datetime.now(timezone.utc),
        )
        async with self._db.session() as session:
            session.add(row)
            await session.commit()
            await session.refresh(row)
        return row

    async def get_by_token_hash(self, token_hash: str) -> OfficeDocumentShare | None:
        async with self._db.session() as session:
            result = await session.execute(
                select(OfficeDocumentShare).where(OfficeDocumentShare.token_hash == token_hash)
            )
            return result.scalar_one_or_none()

    async def list_for_binding(self, binding_id: str) -> list[OfficeDocumentShare]:
        async with self._db.session() as session:
            result = await session.execute(
                select(OfficeDocumentShare)
                .where(OfficeDocumentShare.binding_id == binding_id)
                .order_by(OfficeDocumentShare.created_at.desc())
            )
            return list(result.scalars().all())

    async def delete(self, share_id: str, binding_id: str) -> bool:
        async with self._db.session() as session:
            result = await session.execute(
                select(OfficeDocumentShare).where(
                    OfficeDocumentShare.share_id == share_id,
                    OfficeDocumentShare.binding_id == binding_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True


class DocumentRevisionRepository:
    def __init__(self, db: OfficeDatabase) -> None:
        self._db: OfficeDatabase = db

    async def create(
        self,
        *,
        binding_id: str,
        file_id: str,
        created_by_user_id: str,
    ) -> OfficeDocumentRevision:
        async with self._db.session() as session:
            result = await session.execute(
                select(func.coalesce(func.max(OfficeDocumentRevision.revision_number), 0))
                .where(OfficeDocumentRevision.binding_id == binding_id)
            )
            max_number = int(result.scalar_one())
            revision_number = max_number + 1
            row = OfficeDocumentRevision(
                revision_id=uuid.uuid4().hex,
                binding_id=binding_id,
                file_id=file_id,
                revision_number=revision_number,
                created_by_user_id=created_by_user_id,
                created_at=datetime.now(timezone.utc),
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

    async def list_for_binding(
        self, binding_id: str, limit: int = 10
    ) -> list[OfficeDocumentRevision]:
        async with self._db.session() as session:
            result = await session.execute(
                select(OfficeDocumentRevision)
                .where(OfficeDocumentRevision.binding_id == binding_id)
                .order_by(OfficeDocumentRevision.revision_number.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def get(
        self, binding_id: str, revision_id: str
    ) -> OfficeDocumentRevision | None:
        async with self._db.session() as session:
            result = await session.execute(
                select(OfficeDocumentRevision).where(
                    OfficeDocumentRevision.binding_id == binding_id,
                    OfficeDocumentRevision.revision_id == revision_id,
                )
            )
            return result.scalar_one_or_none()


class DocumentEventRepository:
    def __init__(self, db: OfficeDatabase) -> None:
        self._db: OfficeDatabase = db

    async def append(
        self,
        *,
        binding_id: str,
        company_id: str,
        event_type: str,
        user_id: str,
        payload: JsonObject,
    ) -> OfficeDocumentEvent:
        row = OfficeDocumentEvent(
            event_id=uuid.uuid4().hex,
            binding_id=binding_id,
            company_id=company_id,
            event_type=event_type,
            user_id=user_id,
            payload_json=json.dumps(payload, ensure_ascii=False),
            created_at=datetime.now(timezone.utc),
        )
        async with self._db.session() as session:
            session.add(row)
            await session.commit()
            await session.refresh(row)
        return row

    async def list_for_binding(
        self, binding_id: str, limit: int = 50
    ) -> list[OfficeDocumentEvent]:
        async with self._db.session() as session:
            result = await session.execute(
                select(OfficeDocumentEvent)
                .where(OfficeDocumentEvent.binding_id == binding_id)
                .order_by(OfficeDocumentEvent.created_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    @staticmethod
    def payload(event: OfficeDocumentEvent) -> JsonObject:
        parsed = cast(object, json.loads(event.payload_json))
        return require_json_object(parsed, "office_document_events.payload_json")
