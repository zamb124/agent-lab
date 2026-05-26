from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.elements import ColumnElement

from core.db.database import get_session_factory
from core.db.jsonb import jsonb_text
from core.db.models.platform import PlatformShortLink
from core.db.utils import get_rowcount
from core.short_links.kinds import SHORT_LINK_KIND_SYNC_CALL_JOIN
from core.short_links.payloads import ShortLinkPayload
from core.types import parse_json_object


def _payload_text(key: str) -> ColumnElement[str | None]:
    return jsonb_text(PlatformShortLink.payload, key)


def _payload_text_eq(key: str, value: str) -> ColumnElement[bool]:
    return _payload_text(key) == value


class ShortLinkRepository:
    """platform_short_links в shared БД."""

    def __init__(self, db_url: str | None = None) -> None:
        self._db_url: str | None = db_url

    async def insert_try(
        self, code: str, kind: str, payload: ShortLinkPayload, expires_at: datetime
    ) -> bool:
        """Возвращает True если вставка прошла, False при дубликате code."""
        factory = await get_session_factory(self._db_url)
        async with factory() as session:
            row = PlatformShortLink(
                code=code,
                kind=kind,
                payload=parse_json_object(payload.model_dump_json(), "short_link.payload"),
                expires_at=expires_at,
            )
            session.add(row)
            try:
                await session.commit()
                return True
            except IntegrityError:
                await session.rollback()
                return False

    async def get_by_code(self, code: str) -> PlatformShortLink | None:
        factory = await get_session_factory(self._db_url)
        async with factory() as session:
            res = await session.execute(
                select(PlatformShortLink).where(PlatformShortLink.code == code)
            )
            return res.scalar_one_or_none()

    async def find_sync_by_link_token(self, link_token: str) -> PlatformShortLink | None:
        factory = await get_session_factory(self._db_url)
        async with factory() as session:
            stmt = (
                select(PlatformShortLink)
                .where(
                    PlatformShortLink.kind == SHORT_LINK_KIND_SYNC_CALL_JOIN,
                    _payload_text_eq("link_token", link_token),
                )
                .limit(1)
            )
            res = await session.execute(stmt)
            return res.scalar_one_or_none()

    async def update_expires_at(self, code: str, expires_at: datetime) -> None:
        factory = await get_session_factory(self._db_url)
        async with factory() as session:
            row = await session.get(PlatformShortLink, code)
            if row is None:
                raise ValueError(f"Короткая ссылка {code} не найдена")
            row.expires_at = expires_at
            await session.commit()

    async def delete_by_code(self, code: str) -> bool:
        factory = await get_session_factory(self._db_url)
        async with factory() as session:
            res = await session.execute(
                delete(PlatformShortLink).where(PlatformShortLink.code == code)
            )
            await session.commit()
            return get_rowcount(res) > 0

    async def delete_by_code_and_kind_returning(
        self, code: str, kind: str
    ) -> PlatformShortLink | None:
        """Атомарно удаляет строку только при совпадении kind; иначе ничего не удаляет."""
        factory = await get_session_factory(self._db_url)
        async with factory() as session:
            stmt = (
                delete(PlatformShortLink)
                .where(PlatformShortLink.code == code, PlatformShortLink.kind == kind)
                .returning(PlatformShortLink)
            )
            cursor = await session.execute(stmt)
            row = cursor.scalars().first()
            await session.commit()
            return row

    async def delete_sync_by_link_token(self, link_token: str) -> int:
        factory = await get_session_factory(self._db_url)
        async with factory() as session:
            stmt = delete(PlatformShortLink).where(
                PlatformShortLink.kind == SHORT_LINK_KIND_SYNC_CALL_JOIN,
                _payload_text_eq("link_token", link_token),
            )
            res = await session.execute(stmt)
            await session.commit()
            return get_rowcount(res)
