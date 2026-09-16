"""Shared A2A Protocol 1.0 helpers for flows tests (hard cut, no 0.3 aliases)."""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from core.a2a.methods import (
    CANCEL_TASK,
    CREATE_TASK_PUSH_NOTIFICATION_CONFIG,
    DELETE_TASK_PUSH_NOTIFICATION_CONFIG,
    GET_TASK,
    GET_TASK_PUSH_NOTIFICATION_CONFIG,
    LIST_TASK_PUSH_NOTIFICATION_CONFIGS,
    SEND_MESSAGE,
    SEND_STREAMING_MESSAGE,
    SUBSCRIBE_TO_TASK,
)

A2A_VERSION_HEADER = "A2A-Version"
A2A_PROTOCOL_VERSION = "1.0"

A2A_HEADERS: dict[str, str] = {A2A_VERSION_HEADER: A2A_PROTOCOL_VERSION}

WIRE_TASK_STATES: frozenset[str] = frozenset(
    {
        "TASK_STATE_SUBMITTED",
        "TASK_STATE_WORKING",
        "TASK_STATE_COMPLETED",
        "TASK_STATE_FAILED",
        "TASK_STATE_CANCELED",
        "TASK_STATE_INPUT_REQUIRED",
        "TASK_STATE_REJECTED",
        "TASK_STATE_AUTH_REQUIRED",
    }
)
A2A_OPEN_STATES = frozenset({"TASK_STATE_SUBMITTED", "TASK_STATE_WORKING"})
A2A_GET_TASK_POLL_SECONDS = 60.0
A2A_GET_TASK_POLL_INTERVAL_SECONDS = 0.3


def a2a_headers(base: dict[str, str] | None = None) -> dict[str, str]:
    """Merges A2A-Version: 1.0 into request headers."""
    merged = dict(base or {})
    merged[A2A_VERSION_HEADER] = A2A_PROTOCOL_VERSION
    return merged


def a2a_text_message(
    text: str,
    *,
    task_id: str | None = None,
    context_id: str | None = None,
) -> dict[str, Any]:
    """ProtoJSON Message: ROLE_USER + Part{text}."""
    message: dict[str, Any] = {
        "messageId": str(uuid.uuid4()),
        "role": "ROLE_USER",
        "parts": [{"text": text}],
    }
    if task_id is not None:
        message["taskId"] = task_id
    if context_id is not None:
        message["contextId"] = context_id
    return message


def a2a_rpc(
    method: str,
    params: dict[str, Any],
    *,
    rpc_id: str | int | None = None,
) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()) if rpc_id is None else rpc_id,
        "method": method,
        "params": params,
    }


def a2a_task(data: dict[str, Any]) -> dict[str, Any]:
    assert "error" not in data, data.get("error")
    task = data.get("result")
    assert isinstance(task, dict), data
    return task


def a2a_task_state(task: dict[str, Any]) -> str:
    status = task.get("status")
    assert isinstance(status, dict), task
    state = status.get("state")
    assert isinstance(state, str) and state, task
    return state


async def a2a_wait_task_completed(
    client: Any,
    headers: dict[str, str],
    *,
    flow_id: str,
    data: dict[str, Any],
    poll_seconds: float = A2A_GET_TASK_POLL_SECONDS,
    poll_interval_seconds: float = A2A_GET_TASK_POLL_INTERVAL_SECONDS,
) -> dict[str, Any]:
    """Poll GetTask after returnImmediately SendMessage until COMPLETED."""
    task = a2a_task(data)
    if a2a_task_state(task) not in A2A_OPEN_STATES:
        assert a2a_task_state(task) == "TASK_STATE_COMPLETED", data
        return data
    task_id = task.get("id")
    assert isinstance(task_id, str) and task_id, data
    deadline = time.monotonic() + poll_seconds
    last = data
    while time.monotonic() < deadline:
        poll = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=headers,
            json=a2a_rpc(GET_TASK, {"id": task_id}),
        )
        assert poll.status_code == 200, poll.text
        last = poll.json()
        polled = a2a_task(last)
        if a2a_task_state(polled) not in A2A_OPEN_STATES:
            assert a2a_task_state(polled) == "TASK_STATE_COMPLETED", last
            return last
        await asyncio.sleep(poll_interval_seconds)
    raise AssertionError(
        f"A2A task {task_id} did not complete within {poll_seconds}s: {last}"
    )


def a2a_send_message(
    text: str,
    *,
    context_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    rpc_id: str | int | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {"message": a2a_text_message(text, context_id=context_id)}
    if metadata is not None:
        params["metadata"] = metadata
    return a2a_rpc(SEND_MESSAGE, params, rpc_id=rpc_id)


def a2a_send_streaming_message(
    text: str,
    *,
    context_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    rpc_id: str | int | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {"message": a2a_text_message(text, context_id=context_id)}
    if metadata is not None:
        params["metadata"] = metadata
    return a2a_rpc(SEND_STREAMING_MESSAGE, params, rpc_id=rpc_id)


__all__ = [
    "A2A_GET_TASK_POLL_INTERVAL_SECONDS",
    "A2A_GET_TASK_POLL_SECONDS",
    "A2A_HEADERS",
    "A2A_OPEN_STATES",
    "A2A_PROTOCOL_VERSION",
    "A2A_VERSION_HEADER",
    "CANCEL_TASK",
    "CREATE_TASK_PUSH_NOTIFICATION_CONFIG",
    "DELETE_TASK_PUSH_NOTIFICATION_CONFIG",
    "GET_TASK",
    "GET_TASK_PUSH_NOTIFICATION_CONFIG",
    "LIST_TASK_PUSH_NOTIFICATION_CONFIGS",
    "SEND_MESSAGE",
    "SEND_STREAMING_MESSAGE",
    "SUBSCRIBE_TO_TASK",
    "WIRE_TASK_STATES",
    "a2a_headers",
    "a2a_rpc",
    "a2a_send_message",
    "a2a_send_streaming_message",
    "a2a_task",
    "a2a_task_state",
    "a2a_text_message",
    "a2a_wait_task_completed",
]
