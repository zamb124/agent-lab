"""Repository for platform-wide LLM model score overlays."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, select

from core.ai.providers import AICapability
from core.ai.scoring import EDITORIAL_PRIOR_CAP, PlatformModelScoreOverlay
from core.db.database import get_session_factory
from core.db.models.platform import LLMModelScore
from core.db.utils import get_rowcount

_EDITORIAL_PRIOR_MIN = -EDITORIAL_PRIOR_CAP
_EDITORIAL_PRIOR_MAX = EDITORIAL_PRIOR_CAP


@dataclass(frozen=True)
class LLMModelScoreUpsertResult:
    row: LLMModelScore
    created: bool
    updated: bool


class LLMModelScoreRepository:
    """CRUD для overlay-строк ``llm_model_scores`` в shared БД."""

    def __init__(self, db_url: str) -> None:
        if db_url == "":
            raise ValueError("LLMModelScoreRepository: db_url не может быть пустым.")
        self._db_url: str = db_url

    async def list_all(self) -> list[LLMModelScore]:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(LLMModelScore).order_by(
                    LLMModelScore.capability,
                    LLMModelScore.provider,
                    LLMModelScore.model_id,
                )
            )
            return list(result.scalars().all())

    async def list_overlays(
        self,
        capability: AICapability | str,
    ) -> dict[tuple[str, str], PlatformModelScoreOverlay]:
        capability_value = _clean_capability(capability)
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(LLMModelScore).where(LLMModelScore.capability == capability_value)
            )
            rows = list(result.scalars().all())
        overlays: dict[tuple[str, str], PlatformModelScoreOverlay] = {}
        for row in rows:
            overlays[(row.provider, row.model_id)] = PlatformModelScoreOverlay(
                enabled=bool(row.enabled),
                editorial_prior=float(row.editorial_prior),
                note=row.note,
            )
        return overlays

    async def get(
        self,
        *,
        provider: str,
        model_id: str,
        capability: AICapability | str,
    ) -> LLMModelScore | None:
        provider = _clean_required(provider, "provider")
        model_id = _clean_required(model_id, "model_id")
        capability_value = _clean_capability(capability)
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(LLMModelScore).where(
                    LLMModelScore.provider == provider,
                    LLMModelScore.model_id == model_id,
                    LLMModelScore.capability == capability_value,
                )
            )
            return result.scalar_one_or_none()

    async def upsert_overlay(
        self,
        *,
        provider: str,
        model_id: str,
        capability: AICapability | str,
        enabled: bool = True,
        editorial_prior: float = 0.0,
        note: str | None = None,
        updated_by_user_id: str | None = None,
    ) -> LLMModelScoreUpsertResult:
        provider = _clean_required(provider, "provider")
        model_id = _clean_required(model_id, "model_id")
        capability_value = _clean_capability(capability)
        prior = _validate_editorial_prior(editorial_prior)
        now = datetime.now(timezone.utc)

        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(LLMModelScore).where(
                    LLMModelScore.provider == provider,
                    LLMModelScore.model_id == model_id,
                    LLMModelScore.capability == capability_value,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                row = LLMModelScore(
                    provider=provider,
                    model_id=model_id,
                    capability=capability_value,
                    enabled=enabled,
                    editorial_prior=prior,
                    note=note,
                    updated_by_user_id=updated_by_user_id,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                await session.commit()
                await session.refresh(row)
                return LLMModelScoreUpsertResult(row=row, created=True, updated=True)

            row.enabled = enabled
            row.editorial_prior = prior
            row.note = note
            row.updated_by_user_id = updated_by_user_id
            row.updated_at = now
            await session.commit()
            await session.refresh(row)
            return LLMModelScoreUpsertResult(row=row, created=False, updated=True)

    async def delete(
        self,
        *,
        provider: str,
        model_id: str,
        capability: AICapability | str,
    ) -> bool:
        provider = _clean_required(provider, "provider")
        model_id = _clean_required(model_id, "model_id")
        capability_value = _clean_capability(capability)
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                delete(LLMModelScore).where(
                    LLMModelScore.provider == provider,
                    LLMModelScore.model_id == model_id,
                    LLMModelScore.capability == capability_value,
                )
            )
            await session.commit()
            return get_rowcount(result) > 0


def _clean_required(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if cleaned == "":
        raise ValueError(f"{field_name} не может быть пустым.")
    return cleaned


def _clean_capability(value: AICapability | str) -> str:
    raw = value.value if isinstance(value, AICapability) else str(value)
    cleaned = raw.strip()
    if cleaned == "":
        raise ValueError("capability не может быть пустым.")
    return AICapability(cleaned).value


def _validate_editorial_prior(value: float) -> float:
    if value < _EDITORIAL_PRIOR_MIN or value > _EDITORIAL_PRIOR_MAX:
        raise ValueError(
            f"editorial_prior должен быть в диапазоне {_EDITORIAL_PRIOR_MIN}..{_EDITORIAL_PRIOR_MAX}"
        )
    return float(value)
