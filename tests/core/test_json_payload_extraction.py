"""JSON payload extraction from LLM responses."""

import pytest

from core.types import extract_json_payload_text, parse_json_value

pytestmark = pytest.mark.unit


def test_extract_json_payload_text_from_markdown_fence() -> None:
    text = 'Here is the result:\n```json\n{"page_title": "Title"}\n```\nDone.'
    extracted = extract_json_payload_text(text)
    assert extracted == '{"page_title": "Title"}'


def test_parse_json_value_accepts_fenced_object() -> None:
    payload = parse_json_value(
        'prefix\n```json\n{"a": 1, "b": "two"}\n```\nsuffix',
        "test.payload",
    )
    assert payload == {"a": 1, "b": "two"}


def test_parse_json_value_accepts_object_embedded_in_prose() -> None:
    payload = parse_json_value(
        'Structured output:\n{"page_title": "Example", "ok": true}\nThanks.',
        "test.payload",
    )
    assert payload == {"page_title": "Example", "ok": True}


def test_parse_json_value_repairs_trailing_commas() -> None:
    payload = parse_json_value('{"items": [1, 2,], "ok": true,}', "test.payload")
    assert payload == {"items": [1, 2], "ok": True}


def test_parse_json_value_repairs_python_literals() -> None:
    payload = parse_json_value('{"ok": True, "missing": None}', "test.payload")
    assert payload == {"ok": True, "missing": None}
