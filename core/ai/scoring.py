from __future__ import annotations

from collections.abc import Iterable

from core.ai.models import AIModelRecord
from core.ai.providers import AICapability
from core.ai.requirements import AIRequestRequirements, model_satisfies_requirements


def score_model_record(
    record: AIModelRecord,
    capability: AICapability,
    requirements: AIRequestRequirements,
    *,
    manual_score: float | None = None,
) -> float:
    if not model_satisfies_requirements(record, capability, requirements):
        return float("-inf")

    score = manual_score if manual_score is not None else 0.0
    if record.is_free is True:
        score += 10.0
    if requirements.tools_required and record.supports_tools:
        score += 5.0
    if requirements.vision_required and record.supports_vision:
        score += 5.0
    if requirements.image_output_required and record.supports_image_output:
        score += 5.0
    if requirements.structured_output and record.supports_json_schema:
        score += 4.0
    if record.context_length is not None:
        score += min(record.context_length / 100_000.0, 10.0)
    if record.metadata_status == "verified":
        score += 1.0
    if record.availability_status == "available":
        score += 1.0
    if record.availability_status in {"disabled", "unavailable", "rate_limited"}:
        score -= 1000.0
    return score


def sort_model_records(
    records: Iterable[AIModelRecord],
    capability: AICapability,
    requirements: AIRequestRequirements,
    *,
    manual_scores: dict[tuple[str, str, AICapability], float] | None = None,
) -> list[AIModelRecord]:
    scores = manual_scores or {}
    return sorted(
        records,
        key=lambda record: score_model_record(
            record,
            capability,
            requirements,
            manual_score=scores.get((record.provider, record.model_id, capability)),
        ),
        reverse=True,
    )
