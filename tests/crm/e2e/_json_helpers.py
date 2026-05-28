"""Сужение JSON-ответов CRM E2E тестов."""

from __future__ import annotations


def json_object(response_payload: object) -> dict[str, object]:
    if not isinstance(response_payload, dict):
        raise AssertionError("expected JSON object response")
    return response_payload


def object_dict(value: object, *, field: str = "value") -> dict[str, object]:
    if not isinstance(value, dict):
        raise AssertionError(f"{field} must be a dict")
    return value


def object_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, object]] = []
    for item in value:
        if isinstance(item, dict):
            rows.append(item)
    return rows


def optional_object_dict(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    return {}


def object_str(value: object, *, field: str = "value") -> str:
    if not isinstance(value, str):
        raise AssertionError(f"{field} must be a string")
    return value
