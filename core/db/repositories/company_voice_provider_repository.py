"""SQL-репозиторий per-company override провайдеров речи (shared БД).

Используется только из `core.clients.voice_resolver`. В сервисах
(apps/voice, apps/flows и т.д.) репозиторий напрямую не дёргается —
только через резолвер.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.db.company_voice_provider_secrets import (
    UNSET_SECRETS,
    SecretsPatchValue,
    is_unset_sentinel,
)
from core.db.database import get_session_factory
from core.db.models.platform import CompanyVoiceProvider
from core.db.utils import get_rowcount

VoiceKind = Literal["stt", "tts", "vad"]


class CompanyVoiceProviderRepository:
    """CRUD для таблицы `company_voice_providers`."""

    def __init__(self, db_url: str) -> None:
        if db_url == "":
            raise ValueError("CompanyVoiceProviderRepository: db_url не может быть пустым.")
        self._db_url: str = db_url

    async def get(self, *, company_id: str, kind: VoiceKind) -> CompanyVoiceProvider | None:
        if company_id == "":
            raise ValueError("company_id не может быть пустым.")
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(CompanyVoiceProvider).where(
                    CompanyVoiceProvider.company_id == company_id,
                    CompanyVoiceProvider.kind == kind,
                )
            )
            return result.scalar_one_or_none()

    async def list_by_company(self, *, company_id: str) -> list[CompanyVoiceProvider]:
        if company_id == "":
            raise ValueError("company_id не может быть пустым.")
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(CompanyVoiceProvider)
                .where(CompanyVoiceProvider.company_id == company_id)
                .order_by(CompanyVoiceProvider.kind)
            )
            return list(result.scalars().all())

    async def upsert(
        self,
        *,
        company_id: str,
        kind: VoiceKind,
        provider: str,
        model: str | None = None,
        voice: str | None = None,
        language: str | None = None,
        sample_rate: int | None = None,
        threshold: float | None = None,
        response_format: str | None = None,
        secrets: SecretsPatchValue = UNSET_SECRETS,
    ) -> CompanyVoiceProvider:
        if company_id == "":
            raise ValueError("company_id не может быть пустым.")
        if provider == "":
            raise ValueError("provider не может быть пустым.")
        now = datetime.now(timezone.utc)
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result_existing = await session.execute(
                select(CompanyVoiceProvider).where(
                    CompanyVoiceProvider.company_id == company_id,
                    CompanyVoiceProvider.kind == kind,
                )
            )
            existing = result_existing.scalar_one_or_none()
            secrets_value: dict[str, str] | None
            if is_unset_sentinel(secrets):
                secrets_value = (
                    dict(existing.secrets) if existing and existing.secrets else None
                )
                if secrets_value is not None:
                    normalized: dict[str, str] = {}
                    for kk, vv in secrets_value.items():
                        if vv != "":
                            normalized[kk] = vv
                    secrets_value = normalized if normalized else None
            elif secrets is None:
                secrets_value = None
            else:
                secrets_value = {
                    kk: vv for kk, vv in secrets.items() if vv != ""
                }
                if not secrets_value:
                    secrets_value = None

            values = {
                "company_id": company_id,
                "kind": kind,
                "provider": provider,
                "model": model,
                "voice": voice,
                "language": language,
                "sample_rate": sample_rate,
                "threshold": threshold,
                "response_format": response_format,
                "secrets": secrets_value,
                "updated_at": now,
            }
            stmt = pg_insert(CompanyVoiceProvider).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["company_id", "kind"],
                set_={
                    "provider": provider,
                    "model": model,
                    "voice": voice,
                    "language": language,
                    "sample_rate": sample_rate,
                    "threshold": threshold,
                    "response_format": response_format,
                    "secrets": secrets_value,
                    "updated_at": now,
                },
            )
            _ = await session.execute(stmt)
            await session.commit()

            result = await session.execute(
                select(CompanyVoiceProvider).where(
                    CompanyVoiceProvider.company_id == company_id,
                    CompanyVoiceProvider.kind == kind,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                message = (
                    "company_voice_providers upsert не вернул запись после вставки "
                    + f"(company_id={company_id!r}, kind={kind!r})"
                )
                raise RuntimeError(
                    message
                )
            return row

    async def delete(self, *, company_id: str, kind: VoiceKind) -> bool:
        if company_id == "":
            raise ValueError("company_id не может быть пустым.")
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                delete(CompanyVoiceProvider).where(
                    CompanyVoiceProvider.company_id == company_id,
                    CompanyVoiceProvider.kind == kind,
                )
            )
            await session.commit()
            return get_rowcount(result) > 0


__all__ = ["CompanyVoiceProviderRepository", "VoiceKind"]
