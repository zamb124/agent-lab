"""Сужение JSON-ответов CRM E2E тестов."""

from __future__ import annotations

from typing import cast


def json_object(response_payload: object) -> dict[str, object]:
    if not isinstance(response_payload, dict):
        raise AssertionError("expected JSON object response")
    return cast(dict[str, object], response_payload)


def object_dict(value: object, *, field: str = "value") -> dict[str, object]:
    if not isinstance(value, dict):
        raise AssertionError(f"{field} must be a dict")
    return cast(dict[str, object], value)


def object_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, object]] = []
    for item in cast(list[object], value):
        if isinstance(item, dict):
            rows.append(cast(dict[str, object], item))
    return rows


def optional_object_dict(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return cast(dict[str, object], value)
    return {}


def object_str(value: object, *, field: str = "value") -> str:
    if not isinstance(value, str):
        raise AssertionError(f"{field} must be a string")
    return value


def mock_llm_queue_with_analyze_spare(responses: list[object]) -> list[object]:
    """TaskIQ + shared mock_llm:responses:flows may consume slots before CRM analyze."""
    if not responses:
        raise ValueError("responses must not be empty")
    primary = responses[-1]
    return [*responses, primary, primary]
