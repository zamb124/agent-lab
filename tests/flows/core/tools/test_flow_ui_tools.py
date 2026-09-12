"""Тулы интерфейса ``ui_render`` / ``ui_navigate`` / ``state_set`` через ``tool.run``.

Тулы знают текущий интерфейс flow только через ``flow_interface_scope``: вне исполнения
flow они падают, внутри — проверяют цели рендера/страницы по документу и ставят события
в очередь state, а данные экрана меняют так же, как любой код меняет state.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.flows.src.runtime.flow_interface_context import (
    current_flow_interface,
    flow_interface_scope,
)
from apps.flows.tools.flow_ui_tools import state_set, ui_navigate, ui_render
from core.flow_ui.document import FlowUIDocument
from core.flow_ui.protocol import CONVERSATION_SLOT_ID, FlowUINavigate, FlowUIRender
from core.state import ExecutionState
from core.state.mutation_policy import FrozenStateFieldError
from core.types import JsonObject, require_json_object


def _state(unique_id: str) -> ExecutionState:
    return ExecutionState(
        task_id=f"task-ui-tools-{unique_id}",
        context_id=f"ctx-ui-tools-{unique_id}",
        user_id="u1",
        session_id=f"flow-ui-tools:{unique_id}",
    )


def _interface() -> FlowUIDocument:
    return FlowUIDocument.model_validate(
        {
            "start_page_id": "main",
            "pages": [
                {
                    "page_id": "main",
                    "blocks": [
                        {"type": "slot", "block_id": "summary"},
                        {
                            "type": "tabs",
                            "block_id": "tabs",
                            "tabs": [{"title": "A", "blocks": [{"type": "slot", "block_id": "tab-slot"}]}],
                        },
                        {"type": "conversation", "block_id": "chat"},
                    ],
                },
                {"page_id": "details", "blocks": []},
            ],
        }
    )


def _payload(raw: object) -> JsonObject:
    return require_json_object(raw, "flow_ui.tool_result")


def test_tool_names_and_schemas_are_the_llm_contract() -> None:
    assert (ui_render.name, ui_navigate.name, state_set.name) == ("ui_render", "ui_navigate", "state_set")
    render_schema = ui_render.parameters
    assert set(render_schema["required"]) == {"slot_id", "blocks"}
    assert render_schema["additionalProperties"] is False
    assert set(ui_navigate.parameters["required"]) == {"page_id"}
    assert set(state_set.parameters["required"]) == {"path", "value"}


def test_interface_is_unavailable_outside_flow_execution() -> None:
    with pytest.raises(RuntimeError, match="outside Flow execution"):
        _ = current_flow_interface()
    with flow_interface_scope(_interface()):
        assert current_flow_interface().start_page_id == "main"
        with flow_interface_scope(_interface().with_embed_overrides(conversation=None, start_page_id="details")):
            assert current_flow_interface().start_page_id == "details"
        assert current_flow_interface().start_page_id == "main"
    with pytest.raises(RuntimeError):
        _ = current_flow_interface()


@pytest.mark.asyncio
async def test_tools_require_interface_scope(unique_id: str) -> None:
    state = _state(unique_id)
    with pytest.raises(RuntimeError, match="outside Flow execution"):
        _ = await ui_render.run(
            {"slot_id": "summary", "blocks": [{"type": "divider", "block_id": "d"}]}, state
        )
    with pytest.raises(RuntimeError, match="outside Flow execution"):
        _ = await ui_navigate.run({"page_id": "details"}, state)
    assert state.pending_ui_events() == []


@pytest.mark.asyncio
async def test_ui_render_into_slot_nested_slot_and_conversation(unique_id: str) -> None:
    state = _state(unique_id)
    with flow_interface_scope(_interface()):
        summary = _payload(
            await ui_render.run(
                {
                    "slot_id": "summary",
                    "blocks": [
                        {"type": "metric", "block_id": "total", "label": "Total", "value": "{total}"},
                        {"type": "section", "block_id": "s", "blocks": [{"type": "divider", "block_id": "d"}]},
                    ],
                },
                state,
            )
        )
        assert summary == {"slot_id": "summary", "block_ids": ["total", "s"]}
        nested = _payload(
            await ui_render.run(
                {"slot_id": "tab-slot", "blocks": [{"type": "divider", "block_id": "x"}]}, state
            )
        )
        assert nested["slot_id"] == "tab-slot"
        card = _payload(
            await ui_render.run(
                {"slot_id": CONVERSATION_SLOT_ID, "blocks": [{"type": "text", "block_id": "card", "markdown": "hi"}]},
                state,
            )
        )
        assert card == {"slot_id": "conversation", "block_ids": ["card"]}

    assert set(state.ui_slots) == {"summary", "tab-slot"}
    assert [block.block_id for block in state.ui_slots["summary"]] == ["total", "s"]
    events = state.pending_ui_events()
    assert len(events) == 3
    assert all(isinstance(event, FlowUIRender) for event in events)
    assert [event.slot_id for event in events if isinstance(event, FlowUIRender)] == [
        "summary",
        "tab-slot",
        CONVERSATION_SLOT_ID,
    ]


@pytest.mark.asyncio
async def test_ui_render_rejects_unknown_slot_and_invalid_blocks(unique_id: str) -> None:
    state = _state(unique_id)
    with flow_interface_scope(_interface()):
        with pytest.raises(ValueError, match=r"unknown slot_id 'chat'; available: \['conversation', 'summary', 'tab-slot'\]"):
            _ = await ui_render.run({"slot_id": "chat", "blocks": [{"type": "divider", "block_id": "d"}]}, state)
        with pytest.raises(ValidationError):
            _ = await ui_render.run({"slot_id": "summary", "blocks": []}, state)
        with pytest.raises(ValidationError):
            _ = await ui_render.run({"slot_id": "summary", "blocks": [{"type": "carousel", "block_id": "d"}]}, state)
        with pytest.raises(ValidationError):
            _ = await ui_render.run(
                {"slot_id": "summary", "blocks": [{"type": "slider", "block_id": "s", "field": "x", "min": 5, "max": 1}]},
                state,
            )
        with pytest.raises(ValidationError):
            _ = await ui_render.run({"slot_id": "summary", "blocks": [{"type": "divider", "block_id": "d"}], "extra": 1}, state)
        with pytest.raises(ValueError, match="is a render target and cannot be rendered"):
            _ = await ui_render.run({"slot_id": "summary", "blocks": [{"type": "slot", "block_id": "inner"}]}, state)
        with pytest.raises(ValueError, match="duplicate block_id 'same'"):
            _ = await ui_render.run(
                {
                    "slot_id": "summary",
                    "blocks": [{"type": "divider", "block_id": "same"}, {"type": "divider", "block_id": "same"}],
                },
                state,
            )
    assert state.ui_slots == {} and state.pending_ui_events() == []


@pytest.mark.asyncio
async def test_ui_navigate_known_and_unknown_page(unique_id: str) -> None:
    state = _state(unique_id)
    with flow_interface_scope(_interface()):
        assert _payload(await ui_navigate.run({"page_id": "details"}, state)) == {"page_id": "details"}
        with pytest.raises(ValueError, match=r"unknown page_id 'nope'; available: \['main', 'details'\]"):
            _ = await ui_navigate.run({"page_id": "nope"}, state)
        with pytest.raises(ValidationError):
            _ = await ui_navigate.run({"page_id": "Bad Page"}, state)
    assert state.pending_ui_events() == [FlowUINavigate(page_id="details")]


@pytest.mark.asyncio
async def test_state_set_writes_any_json_by_dotted_path(unique_id: str) -> None:
    state = _state(unique_id)
    assert _payload(await state_set.run({"path": "total", "value": 42}, state)) == {"path": "total", "value": 42}
    assert _payload(await state_set.run({"path": " order.customer.email ", "value": "a@b.c"}, state)) == {
        "path": "order.customer.email",
        "value": "a@b.c",
    }
    _ = await state_set.run({"path": "order.items", "value": [{"sku": "a"}, {"sku": "b"}]}, state)
    _ = await state_set.run({"path": "flag", "value": None}, state)
    assert state["total"] == 42
    assert state["order"] == {"customer": {"email": "a@b.c"}, "items": [{"sku": "a"}, {"sku": "b"}]}
    assert state["flag"] is None
    assert state.pending_ui_events() == []


@pytest.mark.asyncio
async def test_state_set_rejects_frozen_and_malformed_paths(unique_id: str) -> None:
    state = _state(unique_id)
    with pytest.raises(FrozenStateFieldError):
        _ = await state_set.run({"path": "task_id", "value": "hijack"}, state)
    with pytest.raises(FrozenStateFieldError):
        _ = await state_set.run({"path": "ui_slots.summary", "value": []}, state)
    with pytest.raises(ValidationError):
        _ = await state_set.run({"path": "", "value": 1}, state)
    with pytest.raises(ValueError, match="invalid state path"):
        _ = await state_set.run({"path": "a..b", "value": 1}, state)
    with pytest.raises(ValidationError):
        _ = await state_set.run({"path": "a"}, state)
    _ = await state_set.run({"path": "scalar", "value": "text"}, state)
    with pytest.raises(ValueError, match="parent must be a JSON object"):
        _ = await state_set.run({"path": "scalar.child", "value": 1}, state)
    assert state.task_id == f"task-ui-tools-{unique_id}"
