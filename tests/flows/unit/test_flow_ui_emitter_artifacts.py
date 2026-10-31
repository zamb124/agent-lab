"""Артефакты Flow UI в Emitter: ``state`` (снимок + JSON Patch) и ``ui`` (render/navigate).

InMemoryEmitter — реальный BaseEmitter без Redis, поэтому здесь проверяется сама логика
проекции: первый ``emit_state`` в Task — снимок, дальше только патчи, без изменений —
тишина; ``ui``-рендер в ленту расширяет проекцию путями своих блоков, включая вложенные.
"""

from __future__ import annotations

import pytest
from a2a.types import TaskArtifactUpdateEvent

from apps.flows.src.flow_ui.runtime import apply_ui_navigate, apply_ui_render
from apps.flows.src.state import ExecutionState
from apps.flows.src.state.state_path import assign_state_path
from apps.flows.src.streaming import InMemoryEmitter
from core.a2a.codec import get_part_data
from core.types import JsonObject, JsonValue
from core.ui_document.document import FlowUIDocument
from core.ui_document.protocol import (
    CONVERSATION_SLOT_ID,
    FLOW_UI_MEDIA_TYPE,
    JSON_MEDIA_TYPE,
    JSON_PATCH_MEDIA_TYPE,
    STATE_ARTIFACT_ID,
    UI_ARTIFACT_ID,
    FlowUINavigate,
    FlowUIRender,
)

pytestmark = [pytest.mark.no_test_doubles]


def _state(unique_id: str) -> ExecutionState:
    return ExecutionState(
        task_id=f"task-{unique_id}",
        context_id=f"ctx-{unique_id}",
        user_id="u1",
        session_id=f"emitter:{unique_id}",
    )


def _interface() -> FlowUIDocument:
    return FlowUIDocument.model_validate(
        {
            "start_page_id": "main",
            "pages": [
                {
                    "page_id": "main",
                    "blocks": [
                        {"type": "text", "block_id": "greeting", "markdown": "Hi {name}, {order.total}"},
                        {"type": "text_input", "block_id": "name-input", "field": "name"},
                        {"type": "slot", "block_id": "details"},
                        {"type": "conversation", "block_id": "chat"},
                    ],
                },
                {"page_id": "second", "blocks": []},
            ],
        }
    )


def _artifact_events(emitter: InMemoryEmitter, artifact_id: str) -> list[TaskArtifactUpdateEvent]:
    return [
        event
        for event in emitter.events
        if isinstance(event, TaskArtifactUpdateEvent) and event.artifact.artifact_id == artifact_id
    ]


def _single_part(event: TaskArtifactUpdateEvent) -> tuple[str, JsonValue]:
    assert len(event.artifact.parts) == 1
    part = event.artifact.parts[0]
    return part.media_type, get_part_data(part)


class TestStateArtifact:
    @pytest.mark.asyncio
    async def test_snapshot_then_patches_then_silence(self, unique_id: str) -> None:
        state = _state(unique_id)
        assign_state_path(state, "name", "Ann")
        assign_state_path(state, "order", {"total": 1, "secret": "x"})
        assign_state_path(state, "unreferenced", "hidden")
        emitter = InMemoryEmitter(state)

        await emitter.emit_state(_interface())
        snapshot = _artifact_events(emitter, STATE_ARTIFACT_ID)
        assert len(snapshot) == 1
        assert snapshot[0].append is False and snapshot[0].last_chunk is False
        assert snapshot[0].artifact.name == STATE_ARTIFACT_ID
        assert _single_part(snapshot[0]) == (JSON_MEDIA_TYPE, {"name": "Ann", "order": {"total": 1}})

        await emitter.emit_state(_interface())
        assert len(_artifact_events(emitter, STATE_ARTIFACT_ID)) == 1

        assign_state_path(state, "order.total", 2)
        assign_state_path(state, "name", None)
        await emitter.emit_state(_interface())
        patches = _artifact_events(emitter, STATE_ARTIFACT_ID)
        assert len(patches) == 2
        assert patches[1].append is True and patches[1].last_chunk is False
        media_type, operations = _single_part(patches[1])
        assert media_type == JSON_PATCH_MEDIA_TYPE
        assert operations == [
            {"op": "replace", "path": "/name", "value": None},
            {"op": "replace", "path": "/order/total", "value": 2},
        ]

    @pytest.mark.asyncio
    async def test_missing_paths_are_absent_and_appear_via_add(self, unique_id: str) -> None:
        state = _state(unique_id)
        emitter = InMemoryEmitter(state)
        await emitter.emit_state(_interface())
        assert _single_part(_artifact_events(emitter, STATE_ARTIFACT_ID)[0]) == (JSON_MEDIA_TYPE, {})

        assign_state_path(state, "name", "Ann")
        await emitter.emit_state(_interface())
        _, operations = _single_part(_artifact_events(emitter, STATE_ARTIFACT_ID)[1])
        assert operations == [{"op": "add", "path": "/name", "value": "Ann"}]

        assign_state_path(state, "order", {"total": 5})
        assign_state_path(state, "name", "")
        await emitter.emit_state(_interface())
        _, operations = _single_part(_artifact_events(emitter, STATE_ARTIFACT_ID)[2])
        assert operations == [
            {"op": "replace", "path": "/name", "value": ""},
            {"op": "add", "path": "/order", "value": {"total": 5}},
        ]

    @pytest.mark.asyncio
    async def test_frozen_fields_never_reach_the_client(self, unique_id: str) -> None:
        state = _state(unique_id)
        emitter = InMemoryEmitter(state)
        interface = FlowUIDocument.model_validate(
            {
                "start_page_id": "main",
                "pages": [
                    {
                        "page_id": "main",
                        "blocks": [{"type": "text", "block_id": "t", "markdown": "{task_id} {session_id} {name}"}],
                    }
                ],
            }
        )
        assign_state_path(state, "name", "Ann")
        await emitter.emit_state(interface)
        assert _single_part(_artifact_events(emitter, STATE_ARTIFACT_ID)[0]) == (JSON_MEDIA_TYPE, {"name": "Ann"})

    @pytest.mark.asyncio
    async def test_rendered_slot_blocks_extend_the_projection(self, unique_id: str) -> None:
        state = _state(unique_id)
        assign_state_path(state, "metrics", {"total": 7})
        emitter = InMemoryEmitter(state)
        await emitter.emit_state(_interface())
        assert _single_part(_artifact_events(emitter, STATE_ARTIFACT_ID)[0]) == (JSON_MEDIA_TYPE, {})

        render = FlowUIRender.model_validate(
            {
                "slot_id": "details",
                "blocks": [
                    {
                        "type": "section",
                        "block_id": "wrap",
                        "blocks": [{"type": "metric", "block_id": "m", "label": "Total", "value": "{metrics.total}"}],
                    }
                ],
            }
        )
        apply_ui_render(state, render)
        await emitter.flush_ui(_interface())
        _, operations = _single_part(_artifact_events(emitter, STATE_ARTIFACT_ID)[1])
        assert operations == [{"op": "add", "path": "/metrics", "value": {"total": 7}}]

        # Замена содержимого slot убирает старые пути из проекции
        apply_ui_render(
            state,
            FlowUIRender.model_validate({"slot_id": "details", "blocks": [{"type": "divider", "block_id": "d"}]}),
        )
        await emitter.flush_ui(_interface())
        _, operations = _single_part(_artifact_events(emitter, STATE_ARTIFACT_ID)[2])
        assert operations == [{"op": "remove", "path": "/metrics"}]


class TestUiArtifact:
    @pytest.mark.asyncio
    async def test_flush_publishes_queued_events_in_order_then_state(self, unique_id: str) -> None:
        state = _state(unique_id)
        emitter = InMemoryEmitter(state)
        render = FlowUIRender.model_validate(
            {"slot_id": "details", "blocks": [{"type": "heading", "block_id": "h", "text": "Hi"}]}
        )
        apply_ui_render(state, render)
        apply_ui_navigate(state, FlowUINavigate(page_id="second"))

        await emitter.flush_ui(_interface())
        assert state.pending_ui_events() == []
        ui_events = _artifact_events(emitter, UI_ARTIFACT_ID)
        assert [event.append for event in ui_events] == [False, True]
        assert all(event.last_chunk is False for event in ui_events)
        assert all(event.artifact.name == UI_ARTIFACT_ID for event in ui_events)
        assert _single_part(ui_events[0]) == (FLOW_UI_MEDIA_TYPE, render.model_dump(mode="json"))
        assert _single_part(ui_events[1]) == (FLOW_UI_MEDIA_TYPE, {"kind": "navigate", "page_id": "second"})
        artifact_order = [
            event.artifact.artifact_id
            for event in emitter.events
            if isinstance(event, TaskArtifactUpdateEvent)
        ]
        assert artifact_order == [UI_ARTIFACT_ID, UI_ARTIFACT_ID, STATE_ARTIFACT_ID]

        await emitter.flush_ui(_interface())
        assert len(emitter.events) == 3

    @pytest.mark.asyncio
    async def test_conversation_render_extends_projection_with_nested_block_paths(self, unique_id: str) -> None:
        state = _state(unique_id)
        assign_state_path(state, "report", {"rows": [{"a": 1}], "title": "Q3"})
        emitter = InMemoryEmitter(state)
        await emitter.emit_state(_interface())

        card = FlowUIRender.model_validate(
            {
                "slot_id": CONVERSATION_SLOT_ID,
                "blocks": [
                    {
                        "type": "section",
                        "block_id": "card",
                        "title": "{report.title}",
                        "blocks": [{"type": "data_table", "block_id": "table", "rows": "report.rows"}],
                    }
                ],
            }
        )
        await emitter.emit_ui_event(card)
        await emitter.emit_state(_interface())
        _, operations = _single_part(_artifact_events(emitter, STATE_ARTIFACT_ID)[1])
        assert operations == [
            {"op": "add", "path": "/report", "value": {"rows": [{"a": 1}], "title": "Q3"}},
        ]
        assert state.ui_slots == {}

    @pytest.mark.asyncio
    async def test_ui_event_payload_keeps_block_defaults_for_the_client(self, unique_id: str) -> None:
        state = _state(unique_id)
        emitter = InMemoryEmitter(state)
        await emitter.emit_ui_event(
            FlowUIRender.model_validate(
                {"slot_id": "details", "blocks": [{"type": "button", "block_id": "b", "label": "Go", "action": {"name": "go"}}]}
            )
        )
        _, payload = _single_part(_artifact_events(emitter, UI_ARTIFACT_ID)[0])
        assert isinstance(payload, dict)
        blocks = payload["blocks"]
        assert isinstance(blocks, list)
        button: JsonObject = blocks[0]  # pyright: ignore[reportAssignmentType]
        assert button["variant"] == "primary" and button["action"] == {"name": "go", "payload": {}}
        assert button["visible_when"] is None
