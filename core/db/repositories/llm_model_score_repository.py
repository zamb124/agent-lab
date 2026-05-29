"""Repository for platform-wide LLM model scoring.

Scores live in shared DB and are consumed by provider-neutral model routing.
The config file may seed rows, but runtime reads this repository as source of truth.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, cast

from sqlalchemy import delete, select

from core.db.database import get_session_factory
from core.db.models.platform import LLMModelScore
from core.db.utils import get_rowcount
from core.types import JsonObject, JsonValue

LLMModelScoreSource = Literal["config_seed", "manual", "benchmark_import"]


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
                    LLMModelScore.score.desc(),
                    LLMModelScore.provider,
                    LLMModelScore.model_id,
                )
            )
            return list(result.scalars().all())

    async def list_enabled_score_map(self) -> dict[tuple[str, str], float]:
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(
                    LLMModelScore.provider,
                    LLMModelScore.model_id,
                    LLMModelScore.score,
                ).where(LLMModelScore.enabled.is_(True))
            )
            rows = cast(Iterable[tuple[str, str, float]], result.all())
            return {
                (provider, model_id): float(score)
                for provider, model_id, score in rows
            }

    async def get(self, *, provider: str, model_id: str) -> LLMModelScore | None:
        provider = _clean_required(provider, "provider")
        model_id = _clean_required(model_id, "model_id")
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(LLMModelScore).where(
                    LLMModelScore.provider == provider,
                    LLMModelScore.model_id == model_id,
                )
            )
            return result.scalar_one_or_none()

    async def upsert(
        self,
        *,
        provider: str,
        model_id: str,
        score: float,
        enabled: bool = True,
        source: LLMModelScoreSource | str = "manual",
        score_dimensions: Mapping[str, JsonValue] | None = None,
        note: str | None = None,
        updated_by_user_id: str | None = None,
        overwrite: bool = True,
    ) -> LLMModelScoreUpsertResult:
        provider = _clean_required(provider, "provider")
        model_id = _clean_required(model_id, "model_id")
        score = _validate_score(score)
        source = _validate_source(source)
        normalized_dimensions = _normalize_score_dimensions(score_dimensions)
        now = datetime.now(timezone.utc)

        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                select(LLMModelScore).where(
                    LLMModelScore.provider == provider,
                    LLMModelScore.model_id == model_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                row = LLMModelScore(
                    provider=provider,
                    model_id=model_id,
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
            result = await self.upsert(
                provider=_required_seed_text(item, "provider"),
                model_id=_required_seed_text(item, "model_id"),
                score=_required_seed_score(item),
                enabled=_optional_seed_enabled(item),
                source="config_seed",
                score_dimensions=_optional_seed_dimensions(item),
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

    async def delete(self, *, provider: str, model_id: str) -> bool:
        provider = _clean_required(provider, "provider")
        model_id = _clean_required(model_id, "model_id")
        session_factory = await get_session_factory(self._db_url)
        async with session_factory() as session:
            result = await session.execute(
                delete(LLMModelScore).where(
                    LLMModelScore.provider == provider,
                    LLMModelScore.model_id == model_id,
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


def _validate_source(value: str) -> LLMModelScoreSource:
    cleaned = _clean_required(value, "source")
    if cleaned == "config_seed":
        return "config_seed"
    if cleaned == "manual":
        return "manual"
    if cleaned == "benchmark_import":
        return "benchmark_import"
    raise ValueError("source должен быть config_seed/manual/benchmark_import")


def _normalize_score_dimensions(raw: Mapping[str, JsonValue] | None) -> JsonObject:
    if raw is None:
        return {}
    dimensions: JsonObject = {}
    for key, value in raw.items():
        cleaned_key = str(key).strip()
        if cleaned_key == "":
            raise ValueError("score_dimensions не может содержать пустой ключ")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"score_dimensions[{cleaned_key!r}] должен быть числом")
        dimensions[cleaned_key] = float(value)
    return dimensions


def _required_seed_text(item: Mapping[str, JsonValue], field_name: str) -> str:
    raw = item.get(field_name)
    if not isinstance(raw, str) or raw.strip() == "":
        raise ValueError(f"{field_name} должен быть непустой строкой")
    return raw.strip()


def _required_seed_score(item: Mapping[str, JsonValue]) -> float:
    raw = item.get("score")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ValueError("score должен быть числом")
    return _validate_score(float(raw))


def _optional_seed_enabled(item: Mapping[str, JsonValue]) -> bool:
    raw = item.get("enabled")
    if raw is None:
        return True
    if not isinstance(raw, bool):
        raise ValueError("enabled должен быть boolean")
    return raw


def _optional_seed_dimensions(item: Mapping[str, JsonValue]) -> JsonObject | None:
    raw = item.get("score_dimensions")
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ValueError("score_dimensions должен быть объектом")
    dimensions: JsonObject = {}
    for key, value in raw.items():
        dimensions[str(key)] = value
    return dimensions


def _optional_seed_note(item: Mapping[str, JsonValue]) -> str | None:
    raw = item.get("note")
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValueError("note должен быть строкой")
    return raw
