"""Карточки платформенных инструментов в ленте: типизированные блоки через render в conversation."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter

from apps.flows.src.runtime_helpers.flow_ui_cards import (
    card_block_id,
    show_action_preview,
    show_action_result,
    show_activity,
    show_browser_preview,
    show_files,
    show_reflection,
    show_skill_activity,
)
from core.files.file_ref import FileRef
from core.flow_ui.document import (
    FlowUIActionPreview,
    FlowUIActionResult,
    FlowUIActivity,
    FlowUIBlockId,
    FlowUIBrowserPreview,
    FlowUIButton,
    FlowUIFileCard,
    FlowUIReflection,
    FlowUISkillActivity,
)
from core.flow_ui.protocol import CONVERSATION_SLOT_ID, FlowUIRender
from core.state import ExecutionState

pytestmark = [pytest.mark.no_test_doubles]

BLOCK_ID_ADAPTER: TypeAdapter[str] = TypeAdapter(FlowUIBlockId)


def _state(unique_id: str) -> ExecutionState:
    return ExecutionState(
        task_id=f"task-cards-{unique_id}",
        context_id=f"ctx-cards-{unique_id}",
        user_id="u1",
        session_id=f"cards:{unique_id}",
    )


class TestCardBlockId:
    @pytest.mark.parametrize(
        ("prefix", "raw", "expected"),
        [
            ("file", "abc123", "file-abc123"),
            ("skill", "CRM Entities", "skill-crm-entities"),
            ("skill", "crm/entities.v2", "skill-crm-entities-v2"),
            ("browser", "--session--", "browser-session"),
            ("plan", "", "plan"),
            ("plan", "///", "plan"),
        ],
    )
    def test_readable_ids_fit_the_grammar(self, prefix: str, raw: str, expected: str) -> None:
        block_id = card_block_id(prefix, raw)
        assert block_id == expected
        assert BLOCK_ID_ADAPTER.validate_python(block_id) == block_id

    def test_long_ids_keep_a_readable_head_and_a_stable_digest(self) -> None:
        raw = "flow_" + "x" * 80 + ":ctx"
        first = card_block_id("session", raw)
        assert first == card_block_id("session", raw)
        assert len(first) <= 64
        assert first.startswith("session-flow_xxxx")
        assert BLOCK_ID_ADAPTER.validate_python(first) == first
        assert card_block_id("session", raw + "!") != first

    def test_boundary_length_is_not_hashed(self) -> None:
        raw = "a" * (64 - len("file") - 1)
        assert card_block_id("file", raw) == f"file-{raw}"
        assert len(card_block_id("file", raw + "a")) <= 64
        assert card_block_id("file", raw + "a") != f"file-{raw}a"


def _only_render(state: ExecutionState) -> FlowUIRender:
    events = state.pending_ui_events()
    assert len(events) == 1
    render = events[0]
    assert isinstance(render, FlowUIRender)
    assert render.slot_id == CONVERSATION_SLOT_ID
    return render


def test_action_preview_has_apply_button_with_payload(unique_id: str) -> None:
    state = _state(unique_id)
    render = show_action_preview(
        state,
        card_id="crm-create",
        title="Create contact",
        summary="Ann, ann@example.com",
        parameters={"name": "Ann", "patch": "{not a template}"},
        apply_action="crm_apply",
        apply_payload={"draft_id": "d1"},
        apply_label="Apply",
    )
    assert render == _only_render(state)
    preview, button = render.blocks
    assert isinstance(preview, FlowUIActionPreview) and isinstance(button, FlowUIButton)
    assert preview.block_id == "crm-create" and preview.parameters == {"name": "Ann", "patch": "{not a template}"}
    assert button.block_id == "crm-create-apply"
    assert button.action is not None
    assert button.action.name == "crm_apply" and button.action.payload == {"draft_id": "d1"}
    assert state.ui_slots == {}


def test_result_activity_browser_reflection_cards(unique_id: str) -> None:
    state = _state(unique_id)
    result = show_action_result(state, card_id="r", title="Created", status="success", summary="ok")
    activity = show_activity(state, card_id="a", title="Searching", status="running", detail="crm")
    browser = show_browser_preview(
        state, card_id="b", url="https://x", title="Site", screenshot_url="https://x/s.png", status="finished"
    )
    reflection = show_reflection(state, card_id="ref", text="Let me reconsider")
    assert state.pending_ui_events() == [result, activity, browser, reflection]
    assert isinstance(result.blocks[0], FlowUIActionResult) and result.blocks[0].status == "success"
    assert isinstance(activity.blocks[0], FlowUIActivity) and activity.blocks[0].detail == "crm"
    assert isinstance(browser.blocks[0], FlowUIBrowserPreview) and browser.blocks[0].screenshot_url == "https://x/s.png"
    assert isinstance(reflection.blocks[0], FlowUIReflection) and reflection.blocks[0].text == "Let me reconsider"


def test_skill_activity_id_derives_from_agent_skill_id(unique_id: str) -> None:
    state = _state(unique_id)
    render = show_skill_activity(state, agent_skill_id="CRM Entities", title="CRM", status="loaded")
    block = render.blocks[0]
    assert isinstance(block, FlowUISkillActivity)
    assert block.block_id == "skill-crm-entities" and block.agent_skill_id == "CRM Entities"


def test_show_files_renders_one_card_per_file_and_requires_file_id(unique_id: str) -> None:
    state = _state(unique_id)
    files = [
        FileRef(file_id="F1", original_name="a.pdf", content_type="application/pdf", file_size=1),
        FileRef(file_id="f-2", original_name="b.png", content_type="image/png", file_size=2),
    ]
    render = show_files(state, files)
    assert [block.block_id for block in render.blocks] == ["file-f1", "file-f-2"]
    assert all(isinstance(block, FlowUIFileCard) and block.file is None for block in render.blocks)
    assert [block.file_id for block in render.blocks if isinstance(block, FlowUIFileCard)] == ["F1", "f-2"]

    url_only = FileRef(url="https://x/x.txt", original_name="x.txt", content_type="text/plain", file_size=0)
    with pytest.raises(ValueError, match="show_files requires FileRef.file_id"):
        _ = show_files(state, [url_only])
    with pytest.raises(ValueError):
        _ = show_files(state, [])
    assert len(state.pending_ui_events()) == 1
