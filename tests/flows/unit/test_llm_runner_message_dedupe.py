"""Idempotent append user/agent messages в рамках одного A2A task_id."""

import json

from apps.flows.src.runtime.a2a_messages import build_assistant_message, build_user_message
from apps.flows.src.runtime.runners.llm_runner import (
    _assistant_message_already_in_task,
    _format_tool_result_content,
    _user_message_already_in_task,
)


def test_user_message_already_in_task_matches_same_task_and_text() -> None:
    task_id = "task-1"
    messages = [
        build_user_message("а что это ?", "n1", context_id="ctx", task_id=task_id),
        build_assistant_message("Mock LLM ответ", "n1", context_id="ctx", task_id=task_id),
    ]
    assert _user_message_already_in_task(messages, "а что это ?", task_id) is True
    assert _user_message_already_in_task(messages, "другое", task_id) is False
    assert _user_message_already_in_task(messages, "а что это ?", "other-task") is False


def test_assistant_message_already_in_task_matches_last_agent_for_task() -> None:
    task_id = "task-1"
    messages = [
        build_user_message("hi", "n1", context_id="ctx", task_id=task_id),
        build_assistant_message("Mock LLM ответ", "n1", context_id="ctx", task_id=task_id),
    ]
    assert _assistant_message_already_in_task(messages, "Mock LLM ответ", task_id) is True
    assert _assistant_message_already_in_task(messages, "другой ответ", task_id) is False


def test_format_tool_result_content_serializes_objects_as_json() -> None:
    payload = {
        "blocks": [{"type": "agent_plan", "plan": {"agent_plan_id": "p1", "steps": []}}],
    }
    encoded = _format_tool_result_content(payload)
    assert json.loads(encoded) == payload
    assert _format_tool_result_content('{"ok": true}') == '{"ok": true}'
