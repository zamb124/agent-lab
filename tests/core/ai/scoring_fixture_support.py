"""Fixture loading and ranking invariant checks for platform LLM scoring tests."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml

from core.ai.free_pool import PlatformFreeModelRecord
from core.ai.models import AIModelRecord
from core.ai.providers import AICapability
from core.ai.scoring import compute_platform_model_score
from core.config import get_settings
from core.config.base import BaseSettings
from core.types import JsonArray, JsonObject, JsonValue, require_json_object
from tests.core.clients.live_llm_provider_helpers import build_scored_free_pool, hints_from_settings

SCORING_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "scoring"
EXPECTATIONS_PATH = SCORING_FIXTURES_DIR / "expectations.yaml"
POOL_RANKING_PATH = SCORING_FIXTURES_DIR / "pool_ranking.json"
SCORE_TOLERANCE = 0.5
REPLAY_SCORE_TOLERANCE = 0.01


@dataclass(frozen=True)
class ModelRef:
    provider: str
    model_id: str


@dataclass(frozen=True)
class OrderingRule:
    above: ModelRef
    below: ModelRef


@dataclass(frozen=True)
class ScoringExpectations:
    must_exist_if_in_catalog: tuple[ModelRef, ...]
    ordering: tuple[OrderingRule, ...]
    router_fallback_max_score: float | None
    penalized_models_max_score: float | None
    penalized_models: tuple[ModelRef, ...]


@dataclass(frozen=True)
class PoolRankingEntry:
    provider: str
    model_id: str
    score: float
    free_reason: str
    breakdown: dict[str, float]


@dataclass(frozen=True)
class PoolRankingSnapshot:
    generated_at: str
    providers: tuple[str, ...]
    settings_hash: str
    models: tuple[PoolRankingEntry, ...]


@dataclass(frozen=True)
class ScoredPoolRow:
    provider: str
    model_id: str
    score: float
    free_reason: str
    breakdown: dict[str, float]

    @property
    def key(self) -> tuple[str, str]:
        return (self.provider, self.model_id)


def _parse_model_ref(raw: JsonObject, field_name: str) -> ModelRef:
    provider_value = raw.get("provider")
    model_id_value = raw.get("model_id")
    if not isinstance(provider_value, str) or not provider_value.strip():
        raise ValueError(f"{field_name}.provider must be a non-empty string")
    if not isinstance(model_id_value, str) or not model_id_value.strip():
        raise ValueError(f"{field_name}.model_id must be a non-empty string")
    return ModelRef(provider=provider_value.strip(), model_id=model_id_value.strip())


def _parse_optional_float(raw: JsonObject, field_name: str) -> float | None:
    value = raw.get(field_name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be numeric")
    return float(value)


def _require_json_array_field(raw: JsonObject, field_name: str) -> JsonArray:
    value = raw.get(field_name)
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be an array")
    return value


def _optional_json_array_field(raw: JsonObject, field_name: str) -> JsonArray:
    if field_name not in raw:
        return []
    return _require_json_array_field(raw, field_name)


def load_expectations() -> ScoringExpectations:
    parsed_yaml = cast(JsonValue, yaml.safe_load(EXPECTATIONS_PATH.read_text(encoding="utf-8")))
    raw = require_json_object(parsed_yaml, "expectations.yaml")

    must_exist: list[ModelRef] = []
    for index, item in enumerate(_optional_json_array_field(raw, "must_exist_if_in_catalog")):
        item_object = require_json_object(item, f"must_exist_if_in_catalog[{index}]")
        must_exist.append(_parse_model_ref(item_object, f"must_exist_if_in_catalog[{index}]"))

    ordering: list[OrderingRule] = []
    for index, item in enumerate(_optional_json_array_field(raw, "ordering")):
        rule_object = require_json_object(item, f"ordering[{index}]")
        above_raw = rule_object.get("above")
        below_raw = rule_object.get("below")
        if not isinstance(above_raw, dict):
            raise ValueError(f"ordering[{index}].above must be an object")
        if not isinstance(below_raw, dict):
            raise ValueError(f"ordering[{index}].below must be an object")
        ordering.append(
            OrderingRule(
                above=_parse_model_ref(require_json_object(above_raw, f"ordering[{index}].above"), f"ordering[{index}].above"),
                below=_parse_model_ref(require_json_object(below_raw, f"ordering[{index}].below"), f"ordering[{index}].below"),
            )
        )

    penalized_models: list[ModelRef] = []
    for index, item in enumerate(_optional_json_array_field(raw, "penalized_models")):
        item_object = require_json_object(item, f"penalized_models[{index}]")
        penalized_models.append(_parse_model_ref(item_object, f"penalized_models[{index}]"))

    return ScoringExpectations(
        must_exist_if_in_catalog=tuple(must_exist),
        ordering=tuple(ordering),
        router_fallback_max_score=_parse_optional_float(raw, "router_fallback_max_score"),
        penalized_models_max_score=_parse_optional_float(raw, "penalized_models_max_score"),
        penalized_models=tuple(penalized_models),
    )


def catalog_fixture_path(provider: str) -> Path:
    return SCORING_FIXTURES_DIR / f"catalog_{provider}.json"


def load_catalog_records(provider: str) -> list[AIModelRecord]:
    path = catalog_fixture_path(provider)
    if not path.is_file():
        return []
    parsed_json = cast(JsonValue, json.loads(path.read_text(encoding="utf-8")))
    if not isinstance(parsed_json, list):
        raise ValueError(f"{path}: expected JSON array")
    records: list[AIModelRecord] = []
    for index, raw_item in enumerate(parsed_json):
        if not isinstance(raw_item, dict):
            raise ValueError(f"{path}: catalog item [{index}] must be an object")
        records.append(AIModelRecord.model_validate(raw_item))
    return records


def load_all_catalog_records(providers: list[str] | None = None) -> dict[str, list[AIModelRecord]]:
    if providers is None:
        providers = sorted(
            path.stem.removeprefix("catalog_")
            for path in SCORING_FIXTURES_DIR.glob("catalog_*.json")
        )
    return {provider: load_catalog_records(provider) for provider in providers}


def _parse_pool_ranking_entry(raw: JsonObject, field_name: str) -> PoolRankingEntry:
    provider_value = raw.get("provider")
    model_id_value = raw.get("model_id")
    score_value = raw.get("score")
    free_reason_value = raw.get("free_reason")
    breakdown_value = raw.get("breakdown")
    if not isinstance(provider_value, str) or not provider_value.strip():
        raise ValueError(f"{field_name}.provider must be a non-empty string")
    if not isinstance(model_id_value, str) or not model_id_value.strip():
        raise ValueError(f"{field_name}.model_id must be a non-empty string")
    if isinstance(score_value, bool) or not isinstance(score_value, (int, float)):
        raise ValueError(f"{field_name}.score must be numeric")
    if not isinstance(free_reason_value, str) or not free_reason_value.strip():
        raise ValueError(f"{field_name}.free_reason must be a non-empty string")
    breakdown: dict[str, float] = {}
    if breakdown_value is not None:
        if not isinstance(breakdown_value, dict):
            raise ValueError(f"{field_name}.breakdown must be an object")
        for key, value in breakdown_value.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{field_name}.breakdown[{key!r}] must be numeric")
            breakdown[str(key)] = float(value)
    return PoolRankingEntry(
        provider=provider_value.strip(),
        model_id=model_id_value.strip(),
        score=float(score_value),
        free_reason=free_reason_value.strip(),
        breakdown=breakdown,
    )


def load_pool_ranking_snapshot() -> PoolRankingSnapshot:
    parsed_json = cast(JsonValue, json.loads(POOL_RANKING_PATH.read_text(encoding="utf-8")))
    raw = require_json_object(parsed_json, "pool_ranking.json")

    generated_at_value = raw.get("generated_at")
    settings_hash_value = raw.get("settings_hash")
    providers_value = raw.get("providers")
    if not isinstance(generated_at_value, str) or not generated_at_value.strip():
        raise ValueError("pool_ranking.json generated_at must be a non-empty string")
    if not isinstance(settings_hash_value, str) or not settings_hash_value.strip():
        raise ValueError("pool_ranking.json settings_hash must be a non-empty string")
    if not isinstance(providers_value, list):
        raise ValueError("pool_ranking.json providers must be an array")

    models_value = _require_json_array_field(raw, "models")

    providers = tuple(
        provider.strip()
        for provider in providers_value
        if isinstance(provider, str) and provider.strip()
    )
    models: list[PoolRankingEntry] = []
    for index, item in enumerate(models_value):
        item_object = require_json_object(item, f"pool_ranking.json models[{index}]")
        models.append(_parse_pool_ranking_entry(item_object, f"models[{index}]"))

    return PoolRankingSnapshot(
        generated_at=generated_at_value.strip(),
        providers=providers,
        settings_hash=settings_hash_value.strip(),
        models=tuple(models),
    )


@dataclass(frozen=True)
class ScoringFixtureBuildResult:
    ranking: PoolRankingSnapshot
    records_by_provider: dict[str, list[AIModelRecord]]


def pool_ranking_snapshot_from_rows(
    *,
    generated_at: str,
    providers: Sequence[str],
    settings_hash_value: str,
    rows: Sequence[ScoredPoolRow],
) -> PoolRankingSnapshot:
    models = tuple(
        PoolRankingEntry(
            provider=row.provider,
            model_id=row.model_id,
            score=row.score,
            free_reason=row.free_reason,
            breakdown=dict(row.breakdown),
        )
        for row in rows
    )
    return PoolRankingSnapshot(
        generated_at=generated_at,
        providers=tuple(providers),
        settings_hash=settings_hash_value,
        models=models,
    )


def compare_pool_ranking_snapshots(
    committed: PoolRankingSnapshot,
    fresh: PoolRankingSnapshot,
) -> list[str]:
    errors: list[str] = []
    committed_map = {(entry.provider, entry.model_id): entry.score for entry in committed.models}
    fresh_map = {(entry.provider, entry.model_id): entry.score for entry in fresh.models}

    for key, committed_score in committed_map.items():
        fresh_score = fresh_map.get(key)
        if fresh_score is None:
            errors.append(f"missing model in fresh snapshot: {key!r}")
            continue
        if abs(committed_score - fresh_score) > SCORE_TOLERANCE:
            errors.append(
                f"score drift for {key!r}: committed={committed_score}, fresh={fresh_score}"
            )

    committed_top = [(entry.provider, entry.model_id) for entry in committed.models[:30]]
    fresh_top = [(entry.provider, entry.model_id) for entry in fresh.models[:30]]
    if committed_top != fresh_top:
        errors.append(f"top-30 order drift: committed={committed_top!r} fresh={fresh_top!r}")

    return errors


def pool_ranking_snapshot_to_json(snapshot: PoolRankingSnapshot) -> str:
    payload: JsonObject = {
        "generated_at": snapshot.generated_at,
        "providers": list(snapshot.providers),
        "settings_hash": snapshot.settings_hash,
        "models": [
            {
                "provider": entry.provider,
                "model_id": entry.model_id,
                "score": entry.score,
                "free_reason": entry.free_reason,
                "breakdown": dict(entry.breakdown),
            }
            for entry in snapshot.models
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def settings_hash(settings: BaseSettings | None = None) -> str:
    resolved = settings or get_settings()
    scoring = resolved.llm.model_scoring
    payload: JsonObject = {
        "dimension_weights": dict(scoring.dimension_weights),
        "editorial_prior_cap": scoring.editorial_prior_cap,
        "hint_blend_ratio": scoring.hint_blend_ratio,
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def catalog_by_key(records_by_provider: dict[str, list[AIModelRecord]]) -> dict[tuple[str, str], AIModelRecord]:
    indexed: dict[tuple[str, str], AIModelRecord] = {}
    for provider_records in records_by_provider.values():
        for record in provider_records:
            indexed[(record.provider, record.model_id)] = record
    return indexed


def pool_rows_from_records(
    records: list[PlatformFreeModelRecord],
    catalog_index: dict[tuple[str, str], AIModelRecord],
    *,
    settings: BaseSettings | None = None,
) -> list[ScoredPoolRow]:
    resolved = settings or get_settings()
    hints = hints_from_settings(resolved)
    scoring_config = resolved.llm.model_scoring
    rows: list[ScoredPoolRow] = []
    for record in records:
        catalog_record = catalog_index.get((record.provider, record.id))
        breakdown: dict[str, float] = {}
        if catalog_record is not None:
            computed = compute_platform_model_score(
                catalog_record,
                AICapability.LLM_CHAT,
                hint=hints.get((record.provider, record.id)),
                scoring_config=scoring_config,
            )
            breakdown = dict(computed.breakdown)
        rows.append(
            ScoredPoolRow(
                provider=record.provider,
                model_id=record.id,
                score=float(record.score),
                free_reason=record.free_reason,
                breakdown=breakdown,
            )
        )
    return rows


def score_index(rows: list[ScoredPoolRow]) -> dict[tuple[str, str], float]:
    return {row.key: row.score for row in rows}


def model_ref_key(ref: ModelRef) -> tuple[str, str]:
    return (ref.provider, ref.model_id)


def assert_scoring_expectations(
    rows: list[ScoredPoolRow],
    catalog_index: dict[tuple[str, str], AIModelRecord],
    expectations: ScoringExpectations | None = None,
) -> None:
    resolved_expectations = expectations or load_expectations()
    scores = score_index(rows)

    for ref in resolved_expectations.must_exist_if_in_catalog:
        key = model_ref_key(ref)
        if key not in catalog_index:
            continue
        assert key in scores, f"expected pool row for {key!r}"

    for rule in resolved_expectations.ordering:
        above_key = model_ref_key(rule.above)
        below_key = model_ref_key(rule.below)
        if above_key not in catalog_index or below_key not in catalog_index:
            continue
        if above_key not in scores or below_key not in scores:
            continue
        assert scores[above_key] > scores[below_key], (
            f"ordering violated: {above_key!r} ({scores[above_key]}) "
            f"should be above {below_key!r} ({scores[below_key]})"
        )

    router_cap = resolved_expectations.router_fallback_max_score
    if router_cap is not None:
        for key, score in scores.items():
            if key[1] in {"openrouter/free", "free"}:
                assert score <= router_cap, f"router fallback {key!r} score {score} > cap {router_cap}"

    penalized_cap = resolved_expectations.penalized_models_max_score
    if penalized_cap is not None:
        for ref in resolved_expectations.penalized_models:
            key = model_ref_key(ref)
            if key not in scores:
                continue
            assert scores[key] <= penalized_cap, (
                f"penalized model {key!r} score {scores[key]} > cap {penalized_cap}"
            )


def replay_scored_pool_from_fixtures(
    providers: list[str] | None = None,
    settings: BaseSettings | None = None,
) -> list[ScoredPoolRow]:
    records_by_provider = load_all_catalog_records(providers)
    pool_records = build_scored_free_pool(records_by_provider, settings)
    catalog_index = catalog_by_key(records_by_provider)
    return pool_rows_from_records(pool_records, catalog_index, settings=settings)
