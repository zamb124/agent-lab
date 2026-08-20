"""SQL-репозиторий журнала cookie consent (shared БД)."""

from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError

from apps.frontend.models import CookieConsentRecord
from core.db.database import get_session_factory
from core.db.models.platform import CookieConsentSqlRecord


class CookieConsentRepository:
    def __init__(self, db_url: str) -> None:
        self._db_url: str = db_url

    async def create(self, record: CookieConsentRecord) -> CookieConsentRecord:
        row = CookieConsentSqlRecord(
            cookie_consent_id=record.cookie_consent_id,
            created_at=record.created_at,
            brand_host=record.brand_host,
            apex_domain=record.apex_domain,
            decision=record.decision,
            analytics_allowed=record.analytics_allowed,
            consent_text_version=record.consent_text_version,
            locale=record.locale,
            request_id=record.request_id,
            user_agent=record.user_agent,
            ip_hash=record.ip_hash,
            supersedes_cookie_consent_id=record.supersedes_cookie_consent_id,
        )
        session_factory = await get_session_factory(self._db_url)
        try:
            async with session_factory() as session:
                session.add(row)
                await session.commit()
        except SQLAlchemyError as exc:
            raise RuntimeError(
                f"cookie consent journal write failed for {record.cookie_consent_id}"
            ) from exc
        return record
