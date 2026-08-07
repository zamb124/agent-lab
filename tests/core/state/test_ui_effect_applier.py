"""UIEffectApplier issuer/causation/idempotency contract."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

import pytest

from core.capabilities.models import (
    CapabilityExecutionContext,
    PlatformEffectEnvelope,
    PlatformEffectOrigin,
    UIApplyEffect,
)
from core.models.flow_interface import default_flow_interface_config
from core.state import ExecutionState
from core.state.flow_ui import FlowUISetDataCommand
from core.state.flow_ui_effects import UIEffectApplier


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
    document = default_flow_interface_config().template.materialize(
        document_id="flow-ui:ctx-1"
    )
    return ExecutionState.model_validate(
        {
            "task_id": "task-1",
            "context_id": "ctx-1",
            "user_id": "user-1",
            "session_id": "flow-1:ctx-1",
            "branch_id": "default",
            "ui_document": document,
            "ui_template_version": document.template_version,
        }
    )


def _envelope(
    *,
    effect_id: str,
    context: CapabilityExecutionContext,
) -> PlatformEffectEnvelope:
    call_id = "call-1"
    return PlatformEffectEnvelope(
        effect_id=effect_id,
        issued_at=datetime.now(UTC),
        origin=PlatformEffectOrigin(
            capability_call_id=call_id,
            causation_id=context.source_tool_call_id or call_id,
            capability_name="ui.update_data",
            execution_token_sha256=sha256(
                context.execution_token.encode("utf-8")
            ).hexdigest(),
            company_id=context.company_id,
            flow_id=context.flow_id,
            branch_id=context.branch_id,
            session_id=context.session_id,
            task_id=context.task_id,
            context_id=context.context_id,
            source_node_id=context.source_node_id,
            source_tool_call_id=context.source_tool_call_id,
        ),
        effect=UIApplyEffect(
            commands=[
                FlowUISetDataCommand(
                    surface_id="main",
                    path="/values/message",
                    value="hello",
                )
            ]
        ),
    )


def test_ui_effect_applier_is_idempotent_by_effect_id() -> None:
    context = _context()
    state = _state()
    envelope = _envelope(effect_id="effect-1", context=context)
    applier = UIEffectApplier()

    first = applier.apply(state, [envelope], context=context)
    assert len(first) == 1
    assert state.ui_applied_effect_ids == ["effect-1"]
    revision_after_first = state.ui_document.revision

    second = applier.apply(state, [envelope], context=context)
    assert second == []
    assert state.ui_document.revision == revision_after_first


def test_ui_effect_applier_rejects_forged_task_binding() -> None:
    context = _context()
    state = _state()
    envelope = _envelope(effect_id="effect-1", context=context)
    forged = envelope.model_copy(
        update={
            "origin": envelope.origin.model_copy(update={"task_id": "forged-task"}),
        }
    )
    with pytest.raises(ValueError, match="task"):
        _ = UIEffectApplier().apply(state, [forged], context=context)
