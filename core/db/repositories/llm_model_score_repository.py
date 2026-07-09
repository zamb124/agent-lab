"""Repository for platform-wide LLM model scoring.

Hints live in shared DB and are blended with catalog signals at refresh time.
The config file may seed hint rows; runtime ranking always recomputes ``score``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, cast

from sqlalchemy import delete, select

from core.ai.providers import AICapability
from core.ai.scoring import (
    PlatformModelScoreHint,
    merge_hint_dimensions,
    split_score_dimensions,
)
from core.db.database import get_session_factory
from core.db.models.platform import LLMModelScore
from core.db.utils import get_rowcount
from core.types import JsonObject, JsonValue

LLMModelScoreSource = Literal["config_seed", "manual", "benchmark_import", "computed"]


@dataclass(frozen=True)
class LLMModelScoreUpsertResult:
    row: LLMModelScore
    created: bool
    updated: bool


class LLMModelScoreRepository:
    """CRUD для ``llm_model_scores`` в shared БД."""

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
                    LLMModelScore.score.desc(),
                    LLMModelScore.provider,
                    LLMModelScore.model_id,
                )
            )
            return list(result.scalars().all())

    async def list_enabled_score_map(
        self,
        capability: AICapability | str,
    ) -> dict[tuple[str, str], float]:
        capability_value = _clean_capability(capability)
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(
                    LLMModelScore.provider,
                    LLMModelScore.model_id,
                    LLMModelScore.score,
                ).where(
                    LLMModelScore.enabled.is_(True),
                    LLMModelScore.capability == capability_value,
                )
            )
            rows = cast(Iterable[tuple[str, str, float]], result.all())
            return {
                (provider, model_id): float(score)
                for provider, model_id, score in rows
            }

    async def list_hints(
        self,
        capability: AICapability | str,
    ) -> dict[tuple[str, str], PlatformModelScoreHint]:
        capability_value = _clean_capability(capability)
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(LLMModelScore).where(LLMModelScore.capability == capability_value)
            )
            rows = list(result.scalars().all())
        hints: dict[tuple[str, str], PlatformModelScoreHint] = {}
        for row in rows:
            editorial_prior, hint_dimensions = split_score_dimensions(row.score_dimensions)
            hints[(row.provider, row.model_id)] = PlatformModelScoreHint(
                editorial_prior=editorial_prior,
                score_dimensions=hint_dimensions,
                enabled=bool(row.enabled),
                source=row.source,
                note=row.note,
            )
        return hints

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

    async def upsert_hints(
        self,
        *,
        provider: str,
        model_id: str,
        capability: AICapability | str,
        enabled: bool = True,
        source: LLMModelScoreSource | str = "manual",
        editorial_prior: float = 0.0,
        score_dimensions: Mapping[str, float] | None = None,
        computed_score: float = 0.0,
        score_breakdown: Mapping[str, float] | None = None,
        note: str | None = None,
        updated_by_user_id: str | None = None,
        overwrite: bool = True,
    ) -> LLMModelScoreUpsertResult:
        provider = _clean_required(provider, "provider")
        model_id = _clean_required(model_id, "model_id")
        capability_value = _clean_capability(capability)
        source = _validate_source(source)
        normalized_dimensions = _normalize_hint_dimensions(
            editorial_prior=editorial_prior,
            score_dimensions=score_dimensions,
            score_breakdown=score_breakdown,
        )
        score = _validate_score(computed_score)
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
                    score=score,
                    enabled=enabled,
                    source=source,
                    score_dimensions=normalized_dimensions,
                    note=note,
                    updated_by_user_id=updated_by_user_id,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                await session.commit()
                await session.refresh(row)
                return LLMModelScoreUpsertResult(row=row, created=True, updated=True)

            if not overwrite:
                return LLMModelScoreUpsertResult(row=row, created=False, updated=False)

            row.score = score
            row.enabled = enabled
            row.source = source
            row.score_dimensions = normalized_dimensions
            row.note = note
            row.updated_by_user_id = updated_by_user_id
            row.updated_at = now
            await session.commit()
            await session.refresh(row)
            return LLMModelScoreUpsertResult(row=row, created=False, updated=True)

    async def upsert(
        self,
        *,
        provider: str,
        model_id: str,
        capability: AICapability | str,
        score: float,
        enabled: bool = True,
        source: LLMModelScoreSource | str = "manual",
        score_dimensions: Mapping[str, JsonValue] | None = None,
        note: str | None = None,
        updated_by_user_id: str | None = None,
        overwrite: bool = True,
    ) -> LLMModelScoreUpsertResult:
        editorial_prior, hint_dimensions = split_score_dimensions(score_dimensions)
        return await self.upsert_hints(
            provider=provider,
            model_id=model_id,
            capability=capability,
            enabled=enabled,
            source=source,
            editorial_prior=editorial_prior,
            score_dimensions=hint_dimensions,
            computed_score=score,
            note=note,
            updated_by_user_id=updated_by_user_id,
            overwrite=overwrite,
        )

    async def update_computed_score(
        self,
        *,
        provider: str,
        model_id: str,
        capability: AICapability | str,
        score: float,
        score_breakdown: Mapping[str, float],
    ) -> None:
        provider = _clean_required(provider, "provider")
        model_id = _clean_required(model_id, "model_id")
        capability_value = _clean_capability(capability)
        validated_score = _validate_score(score)
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
                return
            editorial_prior, hint_dimensions = split_score_dimensions(row.score_dimensions)
            row.score = validated_score
            row.source = "computed"
            row.score_dimensions = _normalize_hint_dimensions(
                editorial_prior=editorial_prior,
                score_dimensions=hint_dimensions,
                score_breakdown=score_breakdown,
            )
            row.updated_at = now
            await session.commit()

    async def seed_many(
        self,
        items: Iterable[Mapping[str, JsonValue]],
        *,
        force_refresh: bool,
        updated_by_user_id: str = "config_seed",
    ) -> dict[str, int]:
        created = 0
        updated = 0
        skipped = 0
        for item in items:
            editorial_prior, hint_dimensions = _seed_hint_fields(item)
            result = await self.upsert_hints(
                provider=_required_seed_text(item, "provider"),
                model_id=_required_seed_text(item, "model_id"),
                capability=_required_seed_capability(item),
                enabled=_optional_seed_enabled(item),
                source="config_seed",
                editorial_prior=editorial_prior,
                score_dimensions=hint_dimensions,
                computed_score=0.0,
                note=_optional_seed_note(item),
                updated_by_user_id=updated_by_user_id,
                overwrite=force_refresh,
            )
            if result.created:
                created += 1
            elif result.updated:
                updated += 1
            else:
                skipped += 1
        return {"created": created, "updated": updated, "skipped": skipped}

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


def _validate_score(value: float) -> float:
    if value < 0 or value > 1000:
        raise ValueError("score должен быть в диапазоне 0..1000")
    return float(value)


def _clean_capability(value: AICapability | str) -> str:
    raw = value.value if isinstance(value, AICapability) else str(value)
    cleaned = raw.strip()
    if cleaned == "":
        raise ValueError("capability не может быть пустым.")
    return AICapability(cleaned).value


def _validate_source(value: str) -> LLMModelScoreSource:
    cleaned = _clean_required(value, "source")
    if cleaned == "config_seed":
        return "config_seed"
    if cleaned == "manual":
        return "manual"
    if cleaned == "benchmark_import":
        return "benchmark_import"
    if cleaned == "computed":
        return "computed"
    raise ValueError("source должен быть config_seed/manual/benchmark_import/computed")


def _normalize_hint_dimensions(
    *,
    editorial_prior: float,
    score_dimensions: Mapping[str, float] | None,
    score_breakdown: Mapping[str, float] | None,
) -> JsonObject:
    merged = merge_hint_dimensions(editorial_prior, score_dimensions or {})
    if score_breakdown is not None:
        for key, value in score_breakdown.items():
            merged[f"$breakdown_{key}"] = float(value)
    return merged


def _required_seed_text(item: Mapping[str, JsonValue], field_name: str) -> str:
    raw = item.get(field_name)
    if not isinstance(raw, str) or raw.strip() == "":
        raise ValueError(f"{field_name} должен быть непустой строкой")
    return raw.strip()


def _required_seed_capability(item: Mapping[str, JsonValue]) -> str:
    raw = item.get("capability")
    if not isinstance(raw, str) or raw.strip() == "":
        raise ValueError("capability должен быть непустой строкой")
    return _clean_capability(raw)


def _optional_seed_enabled(item: Mapping[str, JsonValue]) -> bool:
    raw = item.get("enabled")
    if raw is None:
        return True
    if not isinstance(raw, bool):
        raise ValueError("enabled должен быть boolean")
    return raw


def _optional_seed_note(item: Mapping[str, JsonValue]) -> str | None:
    raw = item.get("note")
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValueError("note должен быть строкой")
    return raw


def _seed_hint_fields(item: Mapping[str, JsonValue]) -> tuple[float, dict[str, float]]:
    raw_dimensions = item.get("score_dimensions")
    dimensions: dict[str, float] = {}
    if raw_dimensions is not None:
        if not isinstance(raw_dimensions, Mapping):
            raise ValueError("score_dimensions должен быть объектом")
        for key, value in raw_dimensions.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"score_dimensions[{key!r}] должен быть числом")
            cleaned_key = str(key).strip()
            if cleaned_key == "" or cleaned_key.startswith("$"):
                raise ValueError("score_dimensions не может содержать пустой или system-ключ")
            dimensions[cleaned_key] = float(value)

    legacy_score = item.get("score")
    if not dimensions:
        if isinstance(legacy_score, bool) or not isinstance(legacy_score, (int, float)):
            raise ValueError("seed item должен содержать score_dimensions или legacy score")
        dimensions["general_chat"] = float(legacy_score)

    editorial_prior_raw = item.get("editorial_prior")
    editorial_prior = 0.0
    if editorial_prior_raw is not None:
        if isinstance(editorial_prior_raw, bool) or not isinstance(editorial_prior_raw, (int, float)):
            raise ValueError("editorial_prior должен быть числом")
        editorial_prior = float(editorial_prior_raw)

    return editorial_prior, dimensions
