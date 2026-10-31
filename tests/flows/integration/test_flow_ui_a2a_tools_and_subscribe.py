"""Flow UI поверх A2A: тулы ``ui_render``/``ui_navigate``/``state_set`` из llm_node и SubscribeToTask.

Один сценарий обязан сойтись по трём каналам: blocking ``SendMessage``, ``GetTask`` и
стрим ``SendStreamingMessage`` (snapshot Task + события durable ledger). Артефакты ``ui`` и
``state`` — обычные A2A Artifacts, поэтому проверяется их порядок, media type и lossless-
восстановление. ``SubscribeToTask`` отдаёт snapshot Task и хвост только событий после него:
для terminal Task стрим состоит из одного snapshot.
"""

from __future__ import annotations

import uuid

import pytest
from httpx2 import AsyncClient

from core.clients.flow_ui_client import FlowUIStateEvent, decode_task_events
from core.context import require_context
from core.types import JsonObject, require_json_object
from core.ui_document.document import FlowUIDocument, FlowUIMetric
from core.ui_document.protocol import (
    FLOW_UI_MEDIA_TYPE,
    JSON_MEDIA_TYPE,
    JSON_PATCH_MEDIA_TYPE,
    STATE_ARTIFACT_ID,
    UI_ARTIFACT_ID,
    FlowUINavigate,
    FlowUIRender,
)
from tests.flows._a2a_v1 import (
    A2A_HEADERS,
    SEND_STREAMING_MESSAGE,
    SUBSCRIBE_TO_TASK,
    a2a_headers,
    a2a_rpc,
)
from tests.flows._flow_ui_session import (
    a2a_get_task,
    a2a_send,
    ensure_flow,
    state_from_task,
    text_message,
    text_of,
    ui_action_message,
    ui_events_from_task,
)
from tests.flows.a2a_conformance.helpers.flows import delete_flow
from tests.flows.a2a_conformance.helpers.rpc import parse_sse_results

pytestmark = [pytest.mark.timeout(120, func_only=True)]


def _interface() -> FlowUIDocument:
    return FlowUIDocument.model_validate(
        {
            "start_page_id": "main",
            "pages": [
                {
                    "page_id": "main",
                    "title": "Main",
                    "blocks": [
                        {"type": "text", "block_id": "total-text", "markdown": "Total: {total}"},
                        {"type": "slot", "block_id": "summary"},
                        {"type": "conversation", "block_id": "conversation"},
                    ],
                },
                {"page_id": "details", "title": "Details", "blocks": []},
            ],
        }
    )


async def _create_ui_tools_flow(client: AsyncClient, flow_id: str) -> None:
    response = await client.post(
        "/flows/api/v1/flows/",
        headers=A2A_HEADERS,
        json={
            "flow_id": flow_id,
            "name": "Flow UI tools",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "llm_node",
                    "prompt": "Render the summary with ui_render, then answer.",
                    "tools": ["ui_render", "ui_navigate", "state_set"],
                },
            },
            "edges": [{"from_node": "main", "to_node": None}],
            "interface": _interface().model_dump(mode="json"),
        },
    )
    assert response.status_code == 200, response.text


async def _stream_rpc(client: AsyncClient, *, flow_id: str, method: str, params: JsonObject) -> list[JsonObject]:
    response = await client.post(
        f"/flows/api/v1/{flow_id}",
        headers=a2a_headers({**A2A_HEADERS, "Accept": "text/event-stream"}),
        json=a2a_rpc(method, params, rpc_id=str(uuid.uuid4())),
        timeout=60,
    )
    assert response.status_code == 200, response.text
    assert "text/event-stream" in response.headers.get("content-type", "")
    return parse_sse_results(response.text)


async def _subscribe(client: AsyncClient, *, flow_id: str, task_id: str) -> list[JsonObject]:
    return await _stream_rpc(client, flow_id=flow_id, method=SUBSCRIBE_TO_TASK, params={"id": task_id})


async def _send_streaming(client: AsyncClient, *, flow_id: str, message: JsonObject) -> list[JsonObject]:
    return await _stream_rpc(
        client, flow_id=flow_id, method=SEND_STREAMING_MESSAGE, params={"message": message}
    )


def _snapshot_task(frame: JsonObject) -> JsonObject:
    result = require_json_object(frame["result"], "frame.result")
    return require_json_object(result.get("task"), "frame.result.task")


def _artifact_updates(frames: list[JsonObject], artifact_id: str) -> list[JsonObject]:
    updates: list[JsonObject] = []
    for frame in frames:
        result = require_json_object(frame["result"], "frame.result")
        update = result.get("artifactUpdate")
        if not isinstance(update, dict):
            continue
        artifact = require_json_object(update.get("artifact"), "artifactUpdate.artifact")
        if artifact.get("artifactId") == artifact_id:
            updates.append(update)
    return updates


def _parts(update: JsonObject) -> list[JsonObject]:
    artifact = require_json_object(update.get("artifact"), "artifact")
    parts = artifact.get("parts")
    assert isinstance(parts, list)
    return [require_json_object(part, "part") for part in parts]


def _replayed_task(frames: list[JsonObject], task_id: str) -> JsonObject:
    """Task из replay-кадров: snapshot первого кадра плюс артефакты всех artifactUpdate."""
    first = require_json_object(frames[0]["result"], "first frame")
    task = dict(require_json_object(first.get("task"), "first frame task"))
    assert task["id"] == task_id
    artifacts: dict[str, JsonObject] = {}
    order: list[str] = []
    for frame in frames[1:]:
        result = require_json_object(frame["result"], "frame.result")
        update = result.get("artifactUpdate")
        if not isinstance(update, dict):
            continue
        artifact = dict(require_json_object(update.get("artifact"), "artifact"))
        artifact_id = str(artifact["artifactId"])
        if update.get("append") and artifact_id in artifacts:
            existing = artifacts[artifact_id]
            existing_parts = existing["parts"]
            assert isinstance(existing_parts, list)
            new_parts = artifact["parts"]
            assert isinstance(new_parts, list)
            existing["parts"] = [*existing_parts, *new_parts]
            continue
        artifacts[artifact_id] = artifact
        if artifact_id not in order:
            order.append(artifact_id)
    task["artifacts"] = [artifacts[artifact_id] for artifact_id in order]
    return task


@pytest.mark.asyncio
async def test_llm_ui_tools_produce_ui_and_state_artifacts_on_every_channel(
    client: AsyncClient,
    app: object,
    unique_id: str,
    mock_llm_with_queue: object,
    sync_tools: object,
    di,
) -> None:
    _ = app, sync_tools
    _ = require_context()
    mock_llm_with_queue(
        [
            {"type": "tool_call", "tool": "state_set", "args": {"path": "total", "value": 42}},
            {
                "type": "tool_call",
                "tool": "ui_render",
                "args": {
                    "slot_id": "summary",
                    "blocks": [
                        {"type": "metric", "block_id": "total-metric", "label": "Total", "value": "{total}"},
                        {"type": "section", "block_id": "wrap", "blocks": [{"type": "divider", "block_id": "d"}]},
                    ],
                },
            },
            {"type": "tool_call", "tool": "ui_navigate", "args": {"page_id": "details"}},
            f"Summary rendered {unique_id}",
        ]
    )
    flow_id = f"a2a_flow_ui_tools_{unique_id}"
    context_id = f"ctx-tools-{unique_id}"
    await _create_ui_tools_flow(client, flow_id)
    try:
        task = await a2a_send(client, flow_id=flow_id, message=text_message(context_id=context_id, text="show"))
        task_id = str(task["id"])
        assert task["status"]["state"] == "TASK_STATE_COMPLETED", task
        assert f"Summary rendered {unique_id}" in text_of(task, "response")

        assert state_from_task(task) == {"total": 42}
        events = ui_events_from_task(task)
        assert len(events) == 2
        render, navigate = events
        assert isinstance(render, FlowUIRender) and render.slot_id == "summary"
        assert [block.block_id for block in render.blocks] == ["total-metric", "wrap"]
        assert isinstance(render.blocks[0], FlowUIMetric) and render.blocks[0].value == "{total}"
        assert isinstance(navigate, FlowUINavigate) and navigate.page_id == "details"

        state = await di.workflow_runtime.get_state(f"{flow_id}:{context_id}")
        assert state is not None
        assert state["total"] == 42
        assert [block.block_id for block in state.ui_slots["summary"]] == ["total-metric", "wrap"]
        assert state.pending_ui_events() == []

        rehydrated = await a2a_get_task(client, flow_id=flow_id, task_id=task_id)
        assert state_from_task(rehydrated) == {"total": 42}
        assert ui_events_from_task(rehydrated) == events

        # Terminal Task: SubscribeToTask — один кадр, snapshot с полными артефактами
        subscribed = await _subscribe(client, flow_id=flow_id, task_id=task_id)
        assert len(subscribed) == 1, subscribed
        snapshot = _snapshot_task(subscribed[0])
        assert snapshot["id"] == task_id
        assert snapshot["status"]["state"] == "TASK_STATE_COMPLETED"
        assert state_from_task(snapshot) == {"total": 42}
        assert ui_events_from_task(snapshot) == events

        # Тот же сценарий стримом: SUBMITTED snapshot, затем события ledger без потерь
        mock_llm_with_queue(
            [
                {"type": "tool_call", "tool": "state_set", "args": {"path": "total", "value": 42}},
                {
                    "type": "tool_call",
                    "tool": "ui_render",
                    "args": {
                        "slot_id": "summary",
                        "blocks": [
                            {"type": "metric", "block_id": "total-metric", "label": "Total", "value": "{total}"},
                            {"type": "section", "block_id": "wrap", "blocks": [{"type": "divider", "block_id": "d"}]},
                        ],
                    },
                },
                {"type": "tool_call", "tool": "ui_navigate", "args": {"page_id": "details"}},
                f"Summary streamed {unique_id}",
            ]
        )
        frames = await _send_streaming(
            client,
            flow_id=flow_id,
            message=text_message(context_id=f"ctx-stream-{unique_id}", text="show"),
        )
        submitted = _snapshot_task(frames[0])
        assert submitted["status"]["state"] == "TASK_STATE_SUBMITTED"
        assert [message["role"] for message in submitted["history"]] == ["ROLE_USER"]
        assert submitted.get("artifacts", []) == []
        replayed = _replayed_task(frames, str(submitted["id"]))
        assert state_from_task(replayed) == {"total": 42}
        assert ui_events_from_task(replayed) == events
        assert f"Summary streamed {unique_id}" in text_of(replayed, "response")
        ui_updates = _artifact_updates(frames, UI_ARTIFACT_ID)
        assert [update.get("append", False) for update in ui_updates] == [False, True]
        assert all(part["mediaType"] == FLOW_UI_MEDIA_TYPE for update in ui_updates for part in _parts(update))
        state_updates = _artifact_updates(frames, STATE_ARTIFACT_ID)
        assert state_updates, frames
        assert _parts(state_updates[0])[0]["mediaType"] == JSON_MEDIA_TYPE
        assert state_updates[0].get("append", False) is False
        assert all(
            part["mediaType"] == JSON_PATCH_MEDIA_TYPE
            for update in state_updates[1:]
            for part in _parts(update)
        )
    finally:
        await delete_flow(client, flow_id)


@pytest.mark.asyncio
async def test_invalid_ui_render_arguments_return_to_the_llm_as_tool_error(
    client: AsyncClient,
    app: object,
    unique_id: str,
    mock_llm_with_queue: object,
    sync_tools: object,
    di,
) -> None:
    _ = app, sync_tools
    _ = require_context()
    mock_llm_with_queue(
        [
            {
                "type": "tool_call",
                "tool": "ui_render",
                "args": {"slot_id": "summary", "blocks": [{"type": "carousel", "block_id": "x"}]},
            },
            f"Recovered {unique_id}",
        ]
    )
    flow_id = f"a2a_flow_ui_badargs_{unique_id}"
    context_id = f"ctx-badargs-{unique_id}"
    await _create_ui_tools_flow(client, flow_id)
    try:
        task = await a2a_send(client, flow_id=flow_id, message=text_message(context_id=context_id, text="show"))
        assert task["status"]["state"] == "TASK_STATE_COMPLETED", task
        assert f"Recovered {unique_id}" in text_of(task, "response")
        assert ui_events_from_task(task) == []
        state = await di.workflow_runtime.get_state(f"{flow_id}:{context_id}")
        assert state is not None and state.ui_slots == {}
    finally:
        await delete_flow(client, flow_id)


@pytest.mark.asyncio
async def test_unknown_navigate_target_fails_the_task_instead_of_guessing(
    client: AsyncClient,
    app: object,
    unique_id: str,
    mock_llm_with_queue: object,
    sync_tools: object,
) -> None:
    _ = app, sync_tools
    _ = require_context()
    mock_llm_with_queue(
        [
            {"type": "tool_call", "tool": "ui_navigate", "args": {"page_id": "nowhere"}},
            "unreachable",
        ]
    )
    flow_id = f"a2a_flow_ui_badpage_{unique_id}"
    context_id = f"ctx-badpage-{unique_id}"
    await _create_ui_tools_flow(client, flow_id)
    try:
        task = await a2a_send(client, flow_id=flow_id, message=text_message(context_id=context_id, text="go"))
        assert task["status"]["state"] == "TASK_STATE_FAILED", task
        assert "unknown page_id 'nowhere'" in str(task["status"])
        assert ui_events_from_task(task) == []
    finally:
        await delete_flow(client, flow_id)


@pytest.mark.asyncio
async def test_subscribe_returns_terminal_snapshot_without_replaying_the_ledger(
    client: AsyncClient,
    app: object,
    unique_id: str, di,
) -> None:
    _ = app
    _ = require_context()
    flow_id = f"a2a_flow_ui_subscribe_{unique_id}"
    context_id = f"ctx-subscribe-{unique_id}"
    _ = await ensure_flow(
        flow_id=flow_id,
        interface=_interface(),
        code=(
            "async def run(args, state):\n"
            "    state['total'] = (state.get('total') or 0) + 1\n"
            "    state['response'] = f\"total={state['total']}\"\n"
            "    return state\n"
        ),
        di=di,
    )
    try:
        first = await a2a_send(
            client,
            flow_id=flow_id,
            message=ui_action_message(context_id=context_id, action="refresh", source="summary"),
        )
        second = await a2a_send(client, flow_id=flow_id, message=text_message(context_id=context_id, text="again"))
        assert first["id"] != second["id"]
        assert state_from_task(first) == {"total": 1}
        assert state_from_task(second) == {"total": 2}

        first_frames = await _subscribe(client, flow_id=flow_id, task_id=str(first["id"]))
        second_frames = await _subscribe(client, flow_id=flow_id, task_id=str(second["id"]))
        for frames, task, expected_total in ((first_frames, first, 1), (second_frames, second, 2)):
            # Terminal Task: только snapshot — события ledger уже учтены в нём и не повторяются
            assert len(frames) == 1, frames
            snapshot_task = _snapshot_task(frames[0])
            assert snapshot_task["id"] == task["id"]
            assert snapshot_task["status"]["state"] == "TASK_STATE_COMPLETED"
            assert state_from_task(snapshot_task) == {"total": expected_total}
            state_events = [
                event for event in decode_task_events(snapshot_task) if isinstance(event, FlowUIStateEvent)
            ]
            assert state_events and state_events[0].state == {"total": expected_total}

        missing = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=a2a_headers({**A2A_HEADERS, "Accept": "text/event-stream"}),
            json=a2a_rpc(SUBSCRIBE_TO_TASK, {"id": f"missing-{unique_id}"}),
            timeout=30,
        )
        assert missing.status_code == 200, missing.text
        assert parse_sse_results(missing.text) == []
    finally:
        await delete_flow(client, flow_id)
