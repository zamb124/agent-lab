"""Каталог модели подменяет reasoning_effort, который эндпоинт отвергает."""

from core.ai.models.model_record import compatible_reasoning_effort
from core.types import JsonObject, parse_json_object


def _raw(text: str) -> JsonObject:
    return parse_json_object(text, "reasoning")


def test_mandatory_reasoning_replaces_none_with_cheapest_supported() -> None:
    effort = compatible_reasoning_effort(
        _raw('{"reasoning": {"mandatory": true, "supported_efforts": ["max", "high", "low"]}}'),
        "none",
    )
    assert effort == "low"


def test_listed_effort_is_kept() -> None:
    raw = _raw('{"reasoning": {"mandatory": true, "supported_efforts": ["low", "high"]}}')
    assert compatible_reasoning_effort(raw, "high") == "high"


def test_optional_reasoning_keeps_none() -> None:
    assert (
        compatible_reasoning_effort(_raw('{"reasoning": {"mandatory": false}}'), "none") == "none"
    )


def test_missing_reasoning_metadata_keeps_effort() -> None:
    assert compatible_reasoning_effort(_raw("{}"), "none") == "none"
