"""SendMessage / GetTask / CancelTask / ListTasks conformance."""

from __future__ import annotations

import asyncio
import uuid

import pytest

from core.a2a.methods import CANCEL_TASK, GET_TASK, LIST_TASKS, SEND_MESSAGE
from tests.flows.a2a_conformance.helpers.flows import create_echo_flow, delete_flow
from tests.flows.a2a_conformance.helpers.rpc import post_rpc, send_message
from tests.flows.a2a_conformance.helpers.schema import assert_valid_task

pytestmark = [pytest.mark.asyncio, pytest.mark.real_taskiq, pytest.mark.timeout(90, func_only=True)]


async def _wait_completed(client, flow_id: str, task_id: str) -> dict:
    for _ in range(40):
        envelope = await post_rpc(
            client, flow_id, GET_TASK, {"id": task_id, "historyLength": 10}
        )
        if "error" in envelope:
            await asyncio.sleep(0.25)
            continue
        task = envelope["result"]
        if isinstance(task, dict):
            _ = assert_valid_task(task)
            state = task.get("status", {}).get("state")
            if state in {
                "TASK_STATE_COMPLETED",
                "TASK_STATE_FAILED",
                "TASK_STATE_INPUT_REQUIRED",
            }:
                return task
        await asyncio.sleep(0.25)
    raise AssertionError(f"task {task_id} did not complete")


async def test_send_message_returns_valid_task(client, unique_id: str) -> None:
    flow_id = f"a2a_conf_send_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        context_id = f"ctx-{unique_id}"
        task = await send_message(
            client, flow_id, f"hello-{unique_id}", context_id=context_id
        )
        assert task["contextId"] == context_id
        task_id = task["id"]
        final = await _wait_completed(client, flow_id, task_id)
        assert final["status"]["state"] == "TASK_STATE_COMPLETED"
    finally:
        await delete_flow(client, flow_id)


async def test_get_task_not_found_error_code(client, unique_id: str) -> None:
    flow_id = f"a2a_conf_get404_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        envelope = await post_rpc(
            client, flow_id, GET_TASK, {"id": f"missing-{uuid.uuid4().hex}"}
        )
        assert envelope["error"]["code"] == -32001
    finally:
        await delete_flow(client, flow_id)


async def test_cancel_task(client, unique_id: str) -> None:
    flow_id = f"a2a_conf_cancel_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        task = await send_message(
            client,
            flow_id,
            "cancel-me",
            context_id=f"ctx-cancel-{unique_id}",
            configuration={"returnImmediately": True},
        )
        task_id = task["id"]
        envelope = await post_rpc(client, flow_id, CANCEL_TASK, {"id": task_id})
        if "result" in envelope:
            _ = assert_valid_task(envelope["result"])
            state = envelope["result"]["status"]["state"]
            assert state in {"TASK_STATE_CANCELED", "TASK_STATE_COMPLETED"}
        else:
            # Already terminal → TaskNotCancelable (-32002) is also valid.
            assert envelope["error"]["code"] in {-32002, -32001}
    finally:
        await delete_flow(client, flow_id)


async def test_list_tasks_returns_page(client, unique_id: str) -> None:
    flow_id = f"a2a_conf_list_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        task = await send_message(
            client, flow_id, "list-me", context_id=f"ctx-list-{unique_id}"
        )
        _ = await _wait_completed(client, flow_id, task["id"])
        envelope = await post_rpc(
            client,
            flow_id,
            LIST_TASKS,
            {"pageSize": 10, "pageToken": "", "contextId": f"ctx-list-{unique_id}"},
        )
        assert "error" not in envelope, envelope
        result = envelope["result"]
        assert "tasks" in result
        assert "nextPageToken" in result
        assert isinstance(result["tasks"], list)
    finally:
        await delete_flow(client, flow_id)


async def test_send_message_return_immediately(client, unique_id: str) -> None:
    """configuration.returnImmediately=true → SUBMITTED without waiting for terminal."""
    flow_id = f"a2a_conf_imm_{unique_id}"
    await create_echo_flow(client, flow_id)
    try:
        task = await send_message(
            client,
            flow_id,
            "immediate",
            context_id=f"ctx-imm-{unique_id}",
            configuration={"returnImmediately": True},
        )
        assert task["status"]["state"] == "TASK_STATE_SUBMITTED"
        final = await _wait_completed(client, flow_id, task["id"])
        assert final["status"]["state"] == "TASK_STATE_COMPLETED"
    finally:
        await delete_flow(client, flow_id)


async def test_send_message_method_constant(client, unique_id: str) -> None:
    assert SEND_MESSAGE == "SendMessage"
