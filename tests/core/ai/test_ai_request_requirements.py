from math import isclose, isinf

from core.ai.models import AIModelRecord, ArtificialAnalysisIndices
from core.ai.providers import AICapability
from core.ai.requirements import AIRequestRequirements, model_satisfies_requirements
from core.ai.scoring import compute_platform_model_score, requirement_bonus


def _chat_record(**overrides: object) -> AIModelRecord:
    payload: dict[str, object] = {
        "provider": "openrouter",
        "model_id": "vendor/model:free",
        "capabilities": (AICapability.LLM_CHAT,),
        "input_modalities": ("text",),
        "output_modalities": ("text",),
        "is_free": True,
    }
    payload.update(overrides)
    return AIModelRecord.model_validate(payload)


def test_model_satisfies_requirements_rejects_missing_tools_vision_image_structured() -> None:
    record = _chat_record()
    capability = AICapability.LLM_CHAT
    assert model_satisfies_requirements(
        record,
        capability,
        AIRequestRequirements(tools_required=True),
    ) is False
    assert model_satisfies_requirements(
        record,
        capability,
        AIRequestRequirements(vision_required=True),
    ) is False
    assert model_satisfies_requirements(
        record,
        capability,
        AIRequestRequirements(image_output_required=True),
    ) is False
    assert model_satisfies_requirements(
        record,
        capability,
        AIRequestRequirements(structured_output=True),
    ) is False


def test_compute_platform_model_score_rejects_unsatisfied_requirements() -> None:
    record = _chat_record()
    result = compute_platform_model_score(
        record,
        AICapability.LLM_CHAT,
        requirements=AIRequestRequirements(tools_required=True),
    )
    assert isinf(result.score)
    assert result.score < 0
    assert result.breakdown == {"rejected": 1.0}


def test_requirement_bonus_adds_tools_vision_structured_and_keeps_aa_indices_out_of_score() -> None:
    record = _chat_record(
        supports_tools=True,
        supports_structured_output=True,
        input_modalities=("text", "image"),
        artificial_analysis=ArtificialAnalysisIndices(
            intelligence_index=40.0,
            coding_index=96.0,
            agentic_index=80.0,
            model_permaslug="vendor/model",
        ),
    )
    requirements = AIRequestRequirements(
        tools_required=True,
        vision_required=True,
        structured_output=True,
    )
    bonus, breakdown = requirement_bonus(record, requirements)
    assert bonus == 14.0
    assert breakdown["requirement_tools"] == 5.0
    assert breakdown["requirement_vision"] == 5.0
    assert breakdown["requirement_structured_output"] == 4.0
    assert breakdown["requirement_coding_index"] == 96.0
    assert breakdown["requirement_agentic_index"] == 80.0

    scored = compute_platform_model_score(
        record,
        AICapability.LLM_CHAT,
        requirements=requirements,
    )
    assert isclose(scored.score, 54.0, abs_tol=1e-9)
    assert scored.breakdown["requirement_coding_index"] == 96.0
    assert scored.breakdown["requirement_agentic_index"] == 80.0
    assert scored.breakdown["aa_intelligence"] == 40.0
