from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from core.ai.models import AIModelRecord, ArtificialAnalysisIndices
from core.ai.providers import AICapability
from core.ai.requirements import AIRequestRequirements, model_satisfies_requirements

_SIZE_RE = re.compile(r"(?<![a-z0-9])(\d+(?:\.\d+)?)\s*([bm])\b", re.IGNORECASE)
_ROUTER_MODEL_IDS = frozenset({"openrouter/free", "free"})
_NON_TEXT_CHAT_OUTPUT = frozenset({"image", "audio", "music", "video"})

EDITORIAL_PRIOR_CAP = 5.0


@dataclass(frozen=True)
class PlatformModelScoreOverlay:
    enabled: bool
    editorial_prior: float
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


def catalog_heuristic(
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
        + created_bonus
        - modality_penalty
        - availability_penalty
    )
    return max(total, 0.0), breakdown


def clamp_editorial_prior(value: float, *, editorial_prior_cap: float = EDITORIAL_PRIOR_CAP) -> float:
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
    aa = record.artificial_analysis
    if aa is not None:
        if requirements.tools_required and aa.coding_index is not None:
            breakdown["requirement_coding_index"] = round(aa.coding_index, 3)
        if aa.agentic_index is not None:
            breakdown["requirement_agentic_index"] = round(aa.agentic_index, 3)
    return bonus, breakdown


def compute_platform_model_score(
    record: AIModelRecord,
    capability: AICapability,
    *,
    overlay: PlatformModelScoreOverlay | None = None,
    requirements: AIRequestRequirements | None = None,
) -> PlatformModelScoreResult:
    if requirements is not None and not model_satisfies_requirements(record, capability, requirements):
        return PlatformModelScoreResult(score=float("-inf"), breakdown={"rejected": 1.0})

    aa = record.artificial_analysis
    if aa is not None:
        base = aa.intelligence_index
        breakdown = {
            "aa_intelligence": round(aa.intelligence_index, 3),
        }
        if aa.coding_index is not None:
            breakdown["aa_coding"] = round(aa.coding_index, 3)
        if aa.agentic_index is not None:
            breakdown["aa_agentic"] = round(aa.agentic_index, 3)
    else:
        base, breakdown = catalog_heuristic(record, capability)

    req_bonus = 0.0
    req_breakdown: dict[str, float] = {}
    if requirements is not None:
        req_bonus, req_breakdown = requirement_bonus(record, requirements)

    editorial_prior = overlay.editorial_prior if overlay is not None else 0.0
    clamped_prior = clamp_editorial_prior(editorial_prior)
    final_score = base + req_bonus + clamped_prior

    breakdown.update(req_breakdown)
    breakdown["base"] = round(base, 3)
    breakdown["editorial_prior"] = round(clamped_prior, 3)
    breakdown["computed_score"] = round(max(final_score, 0.0), 3)

    return PlatformModelScoreResult(
        score=max(final_score, 0.0),
        breakdown=breakdown,
    )


def normalize_aa_model_slug(model_id: str) -> str:
    cleaned = model_id.strip().lower()
    if cleaned.endswith(":free"):
        return cleaned[: -len(":free")]
    return cleaned


def _aa_last_segment(slug: str) -> str:
    return slug.rsplit("/", 1)[-1]


def attach_artificial_analysis(
    records: Sequence[AIModelRecord],
    indices_by_slug: Mapping[str, ArtificialAnalysisIndices],
) -> list[AIModelRecord]:
    last_segment_to_slugs: dict[str, list[str]] = {}
    for slug in indices_by_slug:
        last_segment_to_slugs.setdefault(_aa_last_segment(slug), []).append(slug)

    attached: list[AIModelRecord] = []
    for record in records:
        matched = _match_artificial_analysis(record, indices_by_slug, last_segment_to_slugs)
        if matched is None:
            attached.append(record)
            continue
        attached.append(record.model_copy(update={"artificial_analysis": matched}))
    return attached


def _match_artificial_analysis(
    record: AIModelRecord,
    indices_by_slug: Mapping[str, ArtificialAnalysisIndices],
    last_segment_to_slugs: Mapping[str, list[str]],
) -> ArtificialAnalysisIndices | None:
    normalized = normalize_aa_model_slug(record.model_id)
    exact = indices_by_slug.get(normalized)
    if exact is not None:
        return exact
    if record.provider == "openrouter":
        return None
    segment = _aa_last_segment(normalized)
    slugs = last_segment_to_slugs.get(segment, [])
    if len(slugs) != 1:
        return None
    return indices_by_slug[slugs[0]]


def sort_model_records(
    records: Iterable[AIModelRecord],
    capability: AICapability,
    requirements: AIRequestRequirements,
    *,
    overlays: Mapping[tuple[str, str], PlatformModelScoreOverlay] | None = None,
) -> list[AIModelRecord]:
    overlay_map = overlays or {}
    return sorted(
        records,
        key=lambda record: compute_platform_model_score(
            record,
            capability,
            overlay=overlay_map.get((record.provider, record.model_id)),
            requirements=requirements,
        ).score,
        reverse=True,
    )
