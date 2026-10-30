"""Применение ui-событий, выпущенных capability gateway для sandbox-кода.

Sandbox не трогает state напрямую: ``ui.render``/``ui.navigate`` возвращаются
из code runner подписанными envelope, а host проверяет привязку к execution
context и manifest, после чего применяет событие как обычный ``FlowUIEvent``.
"""

from __future__ import annotations

from hashlib import sha256

from core.capabilities.models import (
    CapabilityExecutionContext,
    CapabilityManifest,
    PlatformEffectEnvelope,
)
from core.flow_ui.document import FlowUIDocument
from core.flow_ui.protocol import FlowUIRender
from core.flow_ui.runtime import (
    apply_ui_navigate,
    apply_ui_render,
    assert_known_page,
    assert_known_slot,
)
from core.state.execution_state import ExecutionState


def apply_capability_platform_effects(
    state: ExecutionState,
    envelopes: list[PlatformEffectEnvelope],
    *,
    context: CapabilityExecutionContext,
    manifest: CapabilityManifest,
    interface: FlowUIDocument,
) -> None:
    effect_ids = [envelope.effect_id for envelope in envelopes]
    if len(effect_ids) != len(set(effect_ids)):
        raise ValueError("Duplicate platform effect_id in code-runner response")
    for envelope in envelopes:
        _verify_effect_origin(envelope, context)
        _verify_manifest(envelope, manifest)
        effect = envelope.effect
        if isinstance(effect, FlowUIRender):
            assert_known_slot(interface, effect.slot_id)
            apply_ui_render(state, effect)
        else:
            assert_known_page(interface, effect.page_id)
            apply_ui_navigate(state, effect)


def _verify_manifest(envelope: PlatformEffectEnvelope, manifest: CapabilityManifest) -> None:
    allowed = {capability.name for capability in manifest.capabilities}
    if envelope.origin.capability_name not in allowed:
        raise ValueError(
            f"Platform effect capability {envelope.origin.capability_name!r} "
            + "is not declared in the execution manifest"
        )


def _verify_effect_origin(
    envelope: PlatformEffectEnvelope,
    context: CapabilityExecutionContext,
) -> None:
    origin = envelope.origin
    expected_digest = sha256(context.execution_token.encode("utf-8")).hexdigest()
    checks = {
        "execution token": (origin.execution_token_sha256, expected_digest),
        "company": (origin.company_id, context.company_id),
        "flow": (origin.flow_id, context.flow_id),
        "branch": (origin.branch_id, context.branch_id),
        "session": (origin.session_id, context.session_id),
        "task": (origin.task_id, context.task_id),
        "context": (origin.context_id, context.context_id),
        "source node": (origin.source_node_id, context.source_node_id),
        "source tool call": (origin.source_tool_call_id, context.source_tool_call_id),
    }
    for label, (actual, expected) in checks.items():
        if actual != expected:
            raise ValueError(f"Platform effect {label} binding mismatch")
    expected_causation = context.source_tool_call_id or origin.capability_call_id
    if origin.causation_id != expected_causation:
        raise ValueError("Platform effect causation binding mismatch")


__all__ = ["apply_capability_platform_effects"]
