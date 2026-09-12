"""ui-события агента поверх ExecutionState: slot хранит последний рендер, лента не копится.

Очередь ``_pending_ui_events`` — приватное состояние runtime: она переживает
``runtime_copy``, не попадает в dump и опустошается только явным ``drain_ui_events``.
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter

from core.flow_ui.document import FlowUIBlock, FlowUIBlockModel, FlowUIDocument
from core.flow_ui.protocol import CONVERSATION_SLOT_ID, FlowUINavigate, FlowUIRender
from core.flow_ui.runtime import (
    apply_ui_navigate,
    apply_ui_render,
    assert_known_page,
    assert_known_slot,
    render_conversation,
    slot_ids,
)
from core.state import ExecutionState
from core.types import JsonObject

BLOCK_ADAPTER: TypeAdapter[FlowUIBlockModel] = TypeAdapter(FlowUIBlock)


def _block(payload: JsonObject) -> FlowUIBlockModel:
    return BLOCK_ADAPTER.validate_python(payload)


def _state(unique_id: str) -> ExecutionState:
    return ExecutionState(
        task_id=f"task-{unique_id}",
        context_id=f"ctx-{unique_id}",
        user_id="u1",
        session_id=f"flow-ui-runtime:{unique_id}",
    )


def _document() -> FlowUIDocument:
    return FlowUIDocument.model_validate(
        {
            "start_page_id": "main",
            "pages": [
                {
                    "page_id": "main",
                    "blocks": [
                        {"type": "slot", "block_id": "top"},
                        {
                            "type": "columns",
                            "block_id": "cols",
                            "columns": [
                                {"width": 6, "blocks": [{"type": "slot", "block_id": "nested-slot"}]},
                                {"width": 6, "blocks": [{"type": "conversation", "block_id": "chat"}]},
                            ],
                        },
                    ],
                },
                {"page_id": "details", "blocks": [{"type": "slot", "block_id": "side"}]},
            ],
        }
    )


class TestTargets:
    def test_slot_ids_include_nested_slots_on_all_pages_and_conversation(self) -> None:
        assert slot_ids(_document()) == {CONVERSATION_SLOT_ID, "top", "nested-slot", "side"}
        assert slot_ids(FlowUIDocument.model_validate({"start_page_id": "p", "pages": [{"page_id": "p"}]})) == {
            CONVERSATION_SLOT_ID
        }

    def test_known_slot_and_page_assertions(self) -> None:
        document = _document()
        assert_known_slot(document, "nested-slot")
        assert_known_slot(document, CONVERSATION_SLOT_ID)
        with pytest.raises(ValueError, match=r"unknown slot_id 'chat'; available: \['conversation', 'nested-slot', 'side', 'top'\]"):
            assert_known_slot(document, "chat")
        assert_known_page(document, "details")
        with pytest.raises(ValueError, match=r"unknown page_id 'nope'; available: \['main', 'details'\]"):
            assert_known_page(document, "nope")


class TestRender:
    def test_slot_render_replaces_previous_blocks_and_queues_event(self, unique_id: str) -> None:
        state = _state(unique_id)
        first = FlowUIRender(slot_id="top", blocks=[_block({"type": "divider", "block_id": "a"})])
        second = FlowUIRender(
            slot_id="top",
            blocks=[
                _block({"type": "heading", "block_id": "h", "text": "Hi"}),
                _block({"type": "section", "block_id": "s", "blocks": [{"type": "divider", "block_id": "d"}]}),
            ],
        )
        apply_ui_render(state, first)
        apply_ui_render(state, second)
        assert [block.block_id for block in state.ui_slots["top"]] == ["h", "s"]
        assert state.pending_ui_events() == [first, second]
        assert state.drain_ui_events() == [first, second]
        assert state.pending_ui_events() == []
        assert [block.block_id for block in state.ui_slots["top"]] == ["h", "s"]

    def test_separate_slots_are_independent(self, unique_id: str) -> None:
        state = _state(unique_id)
        apply_ui_render(state, FlowUIRender(slot_id="top", blocks=[_block({"type": "divider", "block_id": "a"})]))
        apply_ui_render(state, FlowUIRender(slot_id="side", blocks=[_block({"type": "divider", "block_id": "a"})]))
        assert set(state.ui_slots) == {"top", "side"}

    def test_conversation_render_is_not_stored_in_state(self, unique_id: str) -> None:
        state = _state(unique_id)
        render = render_conversation(state, [_block({"type": "text", "block_id": "card", "markdown": "x"})])
        assert render.slot_id == CONVERSATION_SLOT_ID
        assert state.ui_slots == {}
        assert state.pending_ui_events() == [render]
        duplicate_ids = [
            _block({"type": "divider", "block_id": "same"}),
            _block({"type": "divider", "block_id": "same"}),
        ]
        # Лента дополняется карточками, поэтому одинаковые block_id между рендерами допустимы
        _ = render_conversation(state, duplicate_ids)
        assert len(state.pending_ui_events()) == 2

    def test_slot_render_requires_unique_block_ids(self, unique_id: str) -> None:
        state = _state(unique_id)
        with pytest.raises(ValueError, match="slot 'top': duplicate block_id 'same'"):
            apply_ui_render(
                state,
                FlowUIRender(
                    slot_id="top",
                    blocks=[
                        _block({"type": "divider", "block_id": "same"}),
                        _block({"type": "section", "block_id": "s", "blocks": [{"type": "divider", "block_id": "same"}]}),
                    ],
                ),
            )
        assert state.ui_slots == {} and state.pending_ui_events() == []

    @pytest.mark.parametrize("target", ["slot", "conversation"])
    def test_render_targets_cannot_be_rendered_even_when_nested(self, unique_id: str, target: str) -> None:
        state = _state(unique_id)
        nested = _block(
            {
                "type": "tabs",
                "block_id": "t",
                "tabs": [{"title": "A", "blocks": [{"type": target, "block_id": "inner"}]}],
            }
        )
        with pytest.raises(ValueError, match=f"{target} 'inner' is a render target and cannot be rendered"):
            apply_ui_render(state, FlowUIRender(slot_id="top", blocks=[nested]))
        with pytest.raises(ValueError, match="is a render target"):
            render_conversation(state, [_block({"type": target, "block_id": "direct"})])
        assert state.pending_ui_events() == []

    def test_render_requires_at_least_one_block(self) -> None:
        with pytest.raises(ValueError):
            _ = FlowUIRender(slot_id="top", blocks=[])


class TestNavigateAndQueue:
    def test_navigate_is_queued_in_order_with_renders(self, unique_id: str) -> None:
        state = _state(unique_id)
        navigate = FlowUINavigate(page_id="details")
        render = FlowUIRender(slot_id="side", blocks=[_block({"type": "divider", "block_id": "d"})])
        apply_ui_navigate(state, navigate)
        apply_ui_render(state, render)
        apply_ui_navigate(state, FlowUINavigate(page_id="main"))
        drained = state.drain_ui_events()
        assert drained[0] == navigate and drained[1] == render
        assert isinstance(drained[2], FlowUINavigate) and drained[2].page_id == "main"

    def test_queue_survives_runtime_copy_but_not_serialization(self, unique_id: str) -> None:
        state = _state(unique_id)
        apply_ui_render(state, FlowUIRender(slot_id="top", blocks=[_block({"type": "divider", "block_id": "d"})]))
        copied = state.runtime_copy()
        assert copied.pending_ui_events() == state.pending_ui_events()
        assert [block.block_id for block in copied.ui_slots["top"]] == ["d"]
        _ = copied.drain_ui_events()
        assert len(state.pending_ui_events()) == 1

        restored = ExecutionState.model_validate(state.model_dump())
        assert restored.pending_ui_events() == []
        assert [block.block_id for block in restored.ui_slots["top"]] == ["d"]
        assert "_pending_ui_events" not in state.model_dump()

    def test_pending_events_are_a_copy(self, unique_id: str) -> None:
        state = _state(unique_id)
        apply_ui_navigate(state, FlowUINavigate(page_id="main"))
        pending = state.pending_ui_events()
        pending.clear()
        assert len(state.pending_ui_events()) == 1
