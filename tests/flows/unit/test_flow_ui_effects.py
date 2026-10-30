"""Ui-события из capability gateway: привязка к execution context, manifest и slot."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

import pytest

from core.capabilities.models import (
    CapabilityDefinition,
    CapabilityExecutionContext,
    CapabilityManifest,
    PlatformEffectEnvelope,
    PlatformEffectOrigin,
)
from core.flow_ui.document import FlowUIDocument, FlowUIMarkdownText
from core.flow_ui.effects import apply_capability_platform_effects
from core.flow_ui.protocol import FlowUINavigate, FlowUIRender
from core.state import ExecutionState


def _context() -> CapabilityExecutionContext:
    return CapabilityExecutionContext(
        company_id="company-1",
        user_id="user-1",
        flow_id="flow-1",
        branch_id="default",
        session_id="flow-1:ctx-1",
        task_id="task-1",
        context_id="ctx-1",
        channel="a2a",
        execution_token="token-1",
        source_node_id="node-1",
        source_tool_call_id="tool-1",
    )


def _state() -> ExecutionState:
    return ExecutionState(
        task_id="task-1", context_id="ctx-1", user_id="user-1", session_id="flow-1:ctx-1"
    )


def _interface() -> FlowUIDocument:
    return FlowUIDocument.model_validate(
        {
            "pages": [
                {
                    "page_id": "main",
                    "title": "Main",
                    "blocks": [
                        {"type": "slot", "block_id": "summary"},
                        {"type": "conversation", "block_id": "conversation"},
                    ],
                },
                {"page_id": "done", "title": "Done", "blocks": []},
            ],
            "start_page_id": "main",
        }
    )


def _manifest(*capability_names: str) -> CapabilityManifest:
    return CapabilityManifest(
        version="test",
        capabilities=[
            CapabilityDefinition(name=name, title=name, description=name)
            for name in capability_names
        ],
    )


def _envelope(
    *,
    effect_id: str,
    context: CapabilityExecutionContext,
    capability_name: str,
    effect: FlowUIRender | FlowUINavigate,
) -> PlatformEffectEnvelope:
    return PlatformEffectEnvelope(
        effect_id=effect_id,
        issued_at=datetime.now(UTC),
        origin=PlatformEffectOrigin(
            capability_call_id="call-1",
            causation_id="tool-1",
            capability_name=capability_name,
            execution_token_sha256=sha256(context.execution_token.encode("utf-8")).hexdigest(),
            company_id=context.company_id,
            flow_id=context.flow_id,
            branch_id=context.branch_id,
            session_id=context.session_id,
            task_id=context.task_id,
            context_id=context.context_id,
            source_node_id=context.source_node_id,
            source_tool_call_id=context.source_tool_call_id,
        ),
        effect=effect,
    )


def _render(slot_id: str) -> FlowUIRender:
    return FlowUIRender(
        slot_id=slot_id,
        blocks=[FlowUIMarkdownText(block_id="hello", markdown="hello")],
    )


def test_render_into_slot_persists_and_queues_event() -> None:
    context = _context()
    state = _state()
    envelope = _envelope(
        effect_id="effect-1",
        context=context,
        capability_name="ui.render",
        effect=_render("summary"),
    )

    apply_capability_platform_effects(
        state, [envelope], context=context, manifest=_manifest("ui.render"), interface=_interface()
    )

    assert [block.block_id for block in state.ui_slots["summary"]] == ["hello"]
    assert state.pending_ui_events() == [envelope.effect]


def test_navigate_to_known_page_queues_event() -> None:
    context = _context()
    state = _state()
    navigate = FlowUINavigate(page_id="done")
    envelope = _envelope(
        effect_id="effect-1", context=context, capability_name="ui.navigate", effect=navigate
    )

    apply_capability_platform_effects(
        state,
        [envelope],
        context=context,
        manifest=_manifest("ui.navigate"),
        interface=_interface(),
    )

    assert state.pending_ui_events() == [navigate]
    assert state.ui_slots == {}


def test_unknown_slot_and_page_are_rejected() -> None:
    context = _context()
    with pytest.raises(ValueError, match="unknown slot_id"):
        apply_capability_platform_effects(
            _state(),
            [
                _envelope(
                    effect_id="effect-1",
                    context=context,
                    capability_name="ui.render",
                    effect=_render("missing"),
                )
            ],
            context=context,
            manifest=_manifest("ui.render"),
            interface=_interface(),
        )
    with pytest.raises(ValueError, match="unknown page_id"):
        apply_capability_platform_effects(
            _state(),
            [
                _envelope(
                    effect_id="effect-1",
                    context=context,
                    capability_name="ui.navigate",
                    effect=FlowUINavigate(page_id="missing"),
                )
            ],
            context=context,
            manifest=_manifest("ui.navigate"),
            interface=_interface(),
        )


def test_duplicate_effect_ids_are_rejected() -> None:
    context = _context()
    envelope = _envelope(
        effect_id="effect-1",
        context=context,
        capability_name="ui.render",
        effect=_render("summary"),
    )
    with pytest.raises(ValueError, match="Duplicate platform effect_id"):
        apply_capability_platform_effects(
            _state(),
            [envelope, envelope],
            context=context,
            manifest=_manifest("ui.render"),
            interface=_interface(),
        )


def test_capability_outside_manifest_is_rejected() -> None:
    context = _context()
    envelope = _envelope(
        effect_id="effect-1",
        context=context,
        capability_name="ui.render",
        effect=_render("summary"),
    )
    with pytest.raises(ValueError, match="not declared in the execution manifest"):
        apply_capability_platform_effects(
            _state(),
            [envelope],
            context=context,
            manifest=_manifest("ui.navigate"),
            interface=_interface(),
        )


def test_forged_task_binding_is_rejected() -> None:
    context = _context()
    envelope = _envelope(
        effect_id="effect-1",
        context=context,
        capability_name="ui.render",
        effect=_render("summary"),
    )
    forged = envelope.model_copy(
        update={"origin": envelope.origin.model_copy(update={"task_id": "forged-task"})}
    )
    with pytest.raises(ValueError, match="task"):
        apply_capability_platform_effects(
            _state(),
            [forged],
            context=context,
            manifest=_manifest("ui.render"),
            interface=_interface(),
        )
