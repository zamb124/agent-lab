from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from core.ai.models import AIModelRecord
from core.ai.providers import AICapability
from core.ai.requirements import AIRequestRequirements, model_satisfies_requirements
from core.config.models import LLMModelScoringConfig
from core.types import JsonObject, JsonValue

_SIZE_RE = re.compile(r"(?<![a-z0-9])(\d+(?:\.\d+)?)\s*([bm])\b", re.IGNORECASE)
_ROUTER_MODEL_IDS = frozenset({"openrouter/free", "free"})
_NON_TEXT_CHAT_OUTPUT = frozenset({"image", "audio", "music", "video"})
_EDITORIAL_PRIOR_DIMENSION_KEY = "$editorial_prior"
_SYSTEM_DIMENSION_PREFIX = "$"

DEFAULT_DIMENSION_WEIGHTS: dict[str, float] = {
    "coding": 1.0,
    "agentic": 0.8,
    "general_chat": 1.0,
    "reasoning": 0.9,
    "roleplay": 0.5,
    "vision": 0.6,
}


@dataclass(frozen=True)
class PlatformModelScoreHint:
    editorial_prior: float
    score_dimensions: dict[str, float]
    enabled: bool
    source: str
    note: str | None


@dataclass(frozen=True)
class PlatformModelScoreResult:
    score: float
    breakdown: dict[str, float]


def model_size_billions(*texts: str) -> float:
    best_size_billions = 0.0
    for text in texts:
        for match in _SIZE_RE.finditer(text or ""):
            value = float(match.group(1))
            unit = match.group(2).lower()
            billions = value if unit == "b" else value / 1000.0
            best_size_billions = max(best_size_billions, billions)
    return best_size_billions


def _raw_catalog_text(record: AIModelRecord) -> str:
    parts: list[str] = [record.model_id]
    for key in ("name", "label", "display_name", "description"):
        value = record.raw.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    return " ".join(parts)


def _is_provider_router_model(record: AIModelRecord) -> bool:
    return record.model_id in _ROUTER_MODEL_IDS


def _modality_mismatch_penalty(record: AIModelRecord, capability: AICapability) -> float:
    if capability != AICapability.LLM_CHAT:
        return 0.0
    output_modalities = {value.lower() for value in record.output_modalities}
    if not output_modalities:
        return 0.0
    if "text" in output_modalities:
        if output_modalities - {"text"}:
            return 0.0
        return 0.0
    if output_modalities & _NON_TEXT_CHAT_OUTPUT:
        return 80.0
    return 40.0


def _free_policy_bonus(record: AIModelRecord) -> float:
    if record.is_free is not True:
        return 0.0
    if record.free_reason == "verified_zero_price" or record.free_reason == "zero_price_catalog":
        return 6.0
    if record.free_reason == "account_free_tier":
        return 4.0
    return 3.0


def _provider_benchmark_bonus(record: AIModelRecord) -> float:
    bonus = 0.0
    for key in ("benchmark", "benchmarks", "evaluations"):
        raw_value = record.raw.get(key)
        if not isinstance(raw_value, Mapping):
            continue
        for nested_key, nested_value in raw_value.items():
            key_lower = str(nested_key).lower()
            if isinstance(nested_value, (int, float)) and not isinstance(nested_value, bool):
                numeric = float(nested_value)
                if "elo" in key_lower:
                    bonus = max(bonus, min(numeric / 20.0, 12.0))
                if "swe" in key_lower or "bench" in key_lower:
                    bonus = max(bonus, min(numeric / 10.0, 15.0))
    return bonus


def base_catalog_score(
    record: AIModelRecord,
    capability: AICapability,
) -> tuple[float, dict[str, float]]:
    if _is_provider_router_model(record):
        breakdown = {
            "router_fallback": 5.0,
        }
        return 5.0, breakdown

    size_billions = model_size_billions(_raw_catalog_text(record))
    size_component = min(size_billions * 0.55, 45.0)

    context_component = 0.0
    if record.context_length is not None:
        context_component = min(record.context_length / 80_000.0, 18.0)

    tools_component = 0.0
    if "tools" in record.supported_parameters or record.supports_tools:
        tools_component = 6.0

    structured_component = 0.0
    if record.supports_structured_output or "structured_outputs" in record.supported_parameters:
        structured_component = 4.0

    free_component = _free_policy_bonus(record)
    metadata_component = 1.0 if record.metadata_status == "verified" else 0.0
    benchmark_component = _provider_benchmark_bonus(record)

    modality_penalty = _modality_mismatch_penalty(record, capability)
    availability_penalty = 0.0
    if record.availability_status in {"disabled", "unavailable", "rate_limited"}:
        availability_penalty = 1000.0
    elif record.availability_status == "available":
        availability_penalty = -1.0

    created_bonus = 0.0
    if record.created is not None and record.created > 0:
        created_bonus = min(record.created / 1_000_000_000.0, 2.0)

    breakdown: dict[str, float] = {
        "catalog_size": round(size_component, 3),
        "catalog_context": round(context_component, 3),
        "catalog_tools": round(tools_component, 3),
        "catalog_structured": round(structured_component, 3),
        "catalog_free": round(free_component, 3),
        "catalog_metadata": round(metadata_component, 3),
        "catalog_benchmark": round(benchmark_component, 3),
        "catalog_created": round(created_bonus, 3),
        "catalog_modality_penalty": round(-modality_penalty, 3),
        "catalog_availability": round(-availability_penalty, 3),
    }
    total = (
        size_component
        + context_component
        + tools_component
        + structured_component
        + free_component
        + metadata_component
        + benchmark_component
        + created_bonus
        - modality_penalty
        - availability_penalty
    )
    return max(total, 0.0), breakdown


def split_score_dimensions(raw_dimensions: Mapping[str, JsonValue] | None) -> tuple[float, dict[str, float]]:
    if raw_dimensions is None:
        return 0.0, {}
    editorial_prior = 0.0
    hints: dict[str, float] = {}
    for key, value in raw_dimensions.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        cleaned_key = str(key).strip()
        if cleaned_key == "":
            continue
        numeric = float(value)
        if cleaned_key == _EDITORIAL_PRIOR_DIMENSION_KEY:
            editorial_prior = numeric
            continue
        if cleaned_key.startswith(_SYSTEM_DIMENSION_PREFIX):
            continue
        hints[cleaned_key] = numeric
    return editorial_prior, hints


def merge_hint_dimensions(
    editorial_prior: float,
    hint_dimensions: Mapping[str, float],
) -> JsonObject:
    merged: JsonObject = {key: float(value) for key, value in hint_dimensions.items()}
    if editorial_prior != 0.0:
        merged[_EDITORIAL_PRIOR_DIMENSION_KEY] = float(editorial_prior)
    return merged


def hint_dimensions_score(
    hint_dimensions: Mapping[str, float],
    *,
    dimension_weights: Mapping[str, float],
) -> tuple[float, dict[str, float]]:
    if not hint_dimensions:
        return 0.0, {}
    weighted_sum = 0.0
    weight_total = 0.0
    breakdown: dict[str, float] = {}
    for dimension, value in hint_dimensions.items():
        weight = dimension_weights.get(dimension, 1.0)
        weighted_sum += float(value) * weight
        weight_total += weight
        breakdown[f"hint_{dimension}"] = round(float(value) * weight, 3)
    if weight_total <= 0.0:
        return 0.0, breakdown
    average = weighted_sum / weight_total
    breakdown["hint_blend"] = round(average, 3)
    return average, breakdown


def clamp_editorial_prior(value: float, *, editorial_prior_cap: float) -> float:
    cap = abs(editorial_prior_cap)
    if value > cap:
        return cap
    if value < -cap:
        return -cap
    return value


def requirement_bonus(
    record: AIModelRecord,
    requirements: AIRequestRequirements,
) -> tuple[float, dict[str, float]]:
    bonus = 0.0
    breakdown: dict[str, float] = {}
    if requirements.tools_required and record.supports_tools:
        bonus += 5.0
        breakdown["requirement_tools"] = 5.0
    if requirements.vision_required and record.supports_vision:
        bonus += 5.0
        breakdown["requirement_vision"] = 5.0
    if requirements.image_output_required and record.supports_image_output:
        bonus += 5.0
        breakdown["requirement_image_output"] = 5.0
    if requirements.structured_output and record.supports_json_schema:
        bonus += 4.0
        breakdown["requirement_structured_output"] = 4.0
    return bonus, breakdown


def compute_platform_model_score(
    record: AIModelRecord,
    capability: AICapability,
    *,
    hint: PlatformModelScoreHint | None = None,
    scoring_config: LLMModelScoringConfig | None = None,
    requirements: AIRequestRequirements | None = None,
) -> PlatformModelScoreResult:
    if requirements is not None and not model_satisfies_requirements(record, capability, requirements):
        return PlatformModelScoreResult(score=float("-inf"), breakdown={"rejected": 1.0})

    config = scoring_config or LLMModelScoringConfig()
    dimension_weights = config.dimension_weights or DEFAULT_DIMENSION_WEIGHTS
    hint_blend_ratio = config.hint_blend_ratio
    editorial_prior_cap = config.editorial_prior_cap

    catalog_total, catalog_breakdown = base_catalog_score(record, capability)

    editorial_prior = 0.0
    hint_dimensions: dict[str, float] = {}
    if hint is not None:
        editorial_prior = hint.editorial_prior
        hint_dimensions = dict(hint.score_dimensions)

    hint_total, hint_breakdown = hint_dimensions_score(
        hint_dimensions,
        dimension_weights=dimension_weights,
    )

    if hint_dimensions:
        blended = catalog_total * (1.0 - hint_blend_ratio) + hint_total * hint_blend_ratio
    else:
        blended = catalog_total

    req_bonus = 0.0
    req_breakdown: dict[str, float] = {}
    if requirements is not None:
        req_bonus, req_breakdown = requirement_bonus(record, requirements)

    clamped_prior = clamp_editorial_prior(editorial_prior, editorial_prior_cap=editorial_prior_cap)
    final_score = blended + req_bonus + clamped_prior

    breakdown: dict[str, float] = {}
    breakdown.update(catalog_breakdown)
    breakdown.update(hint_breakdown)
    breakdown.update(req_breakdown)
    breakdown["catalog_base"] = round(catalog_total, 3)
    breakdown["blended_base"] = round(blended, 3)
    breakdown["editorial_prior"] = round(clamped_prior, 3)
    breakdown["computed_score"] = round(max(final_score, 0.0), 3)

    return PlatformModelScoreResult(
        score=max(final_score, 0.0),
        breakdown=breakdown,
    )


def score_model_record(
    record: AIModelRecord,
    capability: AICapability,
    requirements: AIRequestRequirements,
    *,
    manual_score: float | None = None,
    scoring_config: LLMModelScoringConfig | None = None,
) -> float:
    hint: PlatformModelScoreHint | None = None
    if manual_score is not None:
        hint = PlatformModelScoreHint(
            editorial_prior=0.0,
            score_dimensions={"general_chat": manual_score},
            enabled=True,
            source="legacy_manual_score",
            note=None,
        )
    result = compute_platform_model_score(
        record,
        capability,
        hint=hint,
        scoring_config=scoring_config,
        requirements=requirements,
    )
    return result.score


def sort_model_records(
    records: Iterable[AIModelRecord],
    capability: AICapability,
    requirements: AIRequestRequirements,
    *,
    hints: Mapping[tuple[str, str], PlatformModelScoreHint] | None = None,
    scoring_config: LLMModelScoringConfig | None = None,
) -> list[AIModelRecord]:
    hint_map = hints or {}
    return sorted(
        records,
        key=lambda record: compute_platform_model_score(
            record,
            capability,
            hint=hint_map.get((record.provider, record.model_id)),
            scoring_config=scoring_config,
            requirements=requirements,
        ).score,
        reverse=True,
    )
