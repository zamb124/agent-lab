"""Host-only application of capability-issued Flow UI effects."""

from __future__ import annotations

from hashlib import sha256

from core.capabilities.models import (
    CapabilityExecutionContext,
    CapabilityManifest,
    PlatformEffectEnvelope,
    UIApplyEffect,
    UINavigateEffect,
    UIResetEffect,
)
from core.models.flow_interface import (
    DEFAULT_CHAT_TEMPLATE_ID,
    DEFAULT_CHAT_TEMPLATE_VERSION,
    default_flow_interface_config,
)
from core.state.execution_state import ExecutionState
from core.state.flow_ui import FlowUICommand, FlowUINavigateCommand, FlowUITransition
from core.state.flow_ui_delta import apply_flow_ui_commands

_MAX_APPLIED_EFFECT_IDS = 512
_TRUSTED_ISSUER = "linnex.capability-gateway"


class UIEffectApplier:
    """Validate and apply trusted platform UI effects onto ExecutionState."""

    def apply(
        self,
        state: ExecutionState,
        envelopes: list[PlatformEffectEnvelope],
        *,
        context: CapabilityExecutionContext,
        manifest: CapabilityManifest | None = None,
    ) -> list[FlowUITransition]:
        if not envelopes:
            return []
        effect_ids = [envelope.effect_id for envelope in envelopes]
        if len(effect_ids) != len(set(effect_ids)):
            raise ValueError("Duplicate platform effect_id in code-runner response")

        applied = set(state.ui_applied_effect_ids)
        pending = [
            envelope for envelope in envelopes if envelope.effect_id not in applied
        ]
        if not pending:
            return []

        document = state.ui_document.model_copy(deep=True)
        transitions: list[FlowUITransition] = []
        accepted_ids: list[str] = []
        for envelope in pending:
            self._verify_effect_origin(envelope, context)
            self._verify_manifest(envelope, manifest)
            effect = envelope.effect
            before = document.model_copy(deep=True)
            commands, expected_revision = self._commands_for_effect(
                document.revision, envelope
            )
            if isinstance(effect, UIResetEffect):
                config = default_flow_interface_config()
                document = config.template.materialize(document_id=before.document_id)
                document.revision = before.revision + 1
            else:
                document = apply_flow_ui_commands(
                    document,
                    commands,
                    expected_revision=expected_revision,
                    allow_system_data=False,
                ).document
            transitions.append(
                FlowUITransition(
                    transition_id=envelope.effect_id,
                    before=before,
                    after=document,
                    source=f"capability:{envelope.origin.capability_name}",
                )
            )
            accepted_ids.append(envelope.effect_id)

        state.ui_document = document
        state.ui_template_version = document.template_version
        state.ui_last_accepted_client_mutation_id = (
            document.last_accepted_client_mutation_id
        )
        state.ui_effect_cursor += len(accepted_ids)
        state.ui_applied_effect_ids = [
            *(
                effect_id
                for effect_id in state.ui_applied_effect_ids
                if effect_id not in accepted_ids
            ),
            *accepted_ids,
        ][-_MAX_APPLIED_EFFECT_IDS:]
        state.ui_conflict = None
        state.queue_ui_transitions(transitions)
        return transitions

    @staticmethod
    def _verify_manifest(
        envelope: PlatformEffectEnvelope,
        manifest: CapabilityManifest | None,
    ) -> None:
        if manifest is None:
            return
        allowed = {capability.name for capability in manifest.capabilities}
        if envelope.origin.capability_name not in allowed:
            raise ValueError(
                f"Platform effect capability {envelope.origin.capability_name!r} "
                + "is not declared in the execution manifest"
            )

    @staticmethod
    def _verify_effect_origin(
        envelope: PlatformEffectEnvelope,
        context: CapabilityExecutionContext,
    ) -> None:
        origin = envelope.origin
        if origin.issuer != _TRUSTED_ISSUER:
            raise ValueError(f"Platform effect issuer mismatch: {origin.issuer!r}")
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
            "source tool call": (
                origin.source_tool_call_id,
                context.source_tool_call_id,
            ),
        }
        for label, (actual, expected) in checks.items():
            if actual != expected:
                raise ValueError(f"Platform effect {label} binding mismatch")
        expected_causation = context.source_tool_call_id or origin.capability_call_id
        if origin.causation_id != expected_causation:
            raise ValueError("Platform effect causation binding mismatch")

    @staticmethod
    def _commands_for_effect(
        document_revision: int,
        envelope: PlatformEffectEnvelope,
    ) -> tuple[list[FlowUICommand], int | None]:
        effect = envelope.effect
        if isinstance(effect, UIApplyEffect):
            return list(effect.commands), effect.expected_revision
        if isinstance(effect, UINavigateEffect):
            return [FlowUINavigateCommand(page_id=effect.page_id)], effect.expected_revision
        if (
            effect.template_id != DEFAULT_CHAT_TEMPLATE_ID
            or effect.template_version != DEFAULT_CHAT_TEMPLATE_VERSION
        ):
            raise ValueError("Unknown Flow UI reset template")
        if effect.expected_revision is not None and effect.expected_revision != document_revision:
            raise ValueError("Flow UI reset revision conflict")
        return [], effect.expected_revision


def apply_capability_platform_effects(
    state: ExecutionState,
    envelopes: list[PlatformEffectEnvelope],
    *,
    context: CapabilityExecutionContext,
    manifest: CapabilityManifest | None = None,
) -> list[FlowUITransition]:
    return UIEffectApplier().apply(
        state,
        envelopes,
        context=context,
        manifest=manifest,
    )


def apply_trusted_ui_commands(
    state: ExecutionState,
    commands: list[FlowUICommand],
    *,
    transition_id: str,
    source: str,
    expected_revision: int | None = None,
    allow_system_data: bool = True,
) -> FlowUITransition:
    before = state.ui_document.model_copy(deep=True)
    document = apply_flow_ui_commands(
        before,
        commands,
        expected_revision=expected_revision,
        allow_system_data=allow_system_data,
    ).document
    transition = FlowUITransition(
        transition_id=transition_id,
        before=before,
        after=document,
        source=source,
    )
    state.ui_document = document
    state.ui_template_version = document.template_version
    state.ui_last_accepted_client_mutation_id = (
        document.last_accepted_client_mutation_id
    )
    state.ui_effect_cursor += 1
    state.ui_conflict = None
    state.queue_ui_transition(transition)
    return transition


__all__ = [
    "UIEffectApplier",
    "apply_capability_platform_effects",
    "apply_trusted_ui_commands",
]
