"""Unit: ProtoJSON Task text extract (A2A 1.0, без Part.kind)."""

from __future__ import annotations

import pytest

from core.a2a.task_json import extract_text_from_task_json


def test_extract_text_from_status_message() -> None:
    task = {
        "status": {
            "state": "TASK_STATE_COMPLETED",
            "message": {
                "role": "ROLE_AGENT",
                "parts": [{"text": "hello from status"}],
            },
        }
    }
    assert extract_text_from_task_json(task) == "hello from status"


def test_extract_text_from_history_role_agent() -> None:
    task = {
        "history": [
            {"role": "ROLE_USER", "parts": [{"text": "q"}]},
            {"role": "ROLE_AGENT", "parts": [{"text": "answer"}]},
        ],
        "status": {"state": "TASK_STATE_COMPLETED"},
    }
    assert extract_text_from_task_json(task) == "answer"


def test_extract_text_from_artifacts() -> None:
    task = {
        "status": {"state": "TASK_STATE_COMPLETED"},
        "artifacts": [{"parts": [{"text": "artifact text"}]}],
    }
    assert extract_text_from_task_json(task) == "artifact text"


def test_extract_text_ignores_kind_field() -> None:
    """0.3 kind не требуется и не мешает, если есть text."""
    task = {
        "status": {
            "state": "TASK_STATE_COMPLETED",
            "message": {"parts": [{"kind": "text", "text": "still works"}]},
        }
    }
    assert extract_text_from_task_json(task) == "still works"


def test_extract_text_raises_when_empty() -> None:
    with pytest.raises(ValueError, match="не содержит текстового ответа"):
        _ = extract_text_from_task_json({"status": {"state": "TASK_STATE_COMPLETED"}})
