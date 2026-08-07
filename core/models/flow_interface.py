"""Design-time Flow UI configuration; chat is the default editable template."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from core.a2a.extensions import A2UI_PLATFORM_CATALOG_ID, PLATFORM_UI_SUBMIT_ACTION
from core.models.base import StrictBaseModel
from core.state.flow_ui import (
    FlowInterfacePolicySnapshot,
    FlowUIAction,
    FlowUIComponent,
    FlowUIContainerLayout,
    FlowUIDataModel,
    FlowUIDocument,
    FlowUIFlexDefinition,
    FlowUIPage,
    FlowUIStackDefinition,
    FlowUISurface,
    LocalizedText,
)
from core.types import JsonObject

DEFAULT_CHAT_TEMPLATE_ID = "linnex.default-chat"
DEFAULT_CHAT_TEMPLATE_VERSION = "1.1.0"


class FlowUIDocumentTemplate(StrictBaseModel):
    template_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    document: FlowUIDocument

    def materialize(self, *, document_id: str) -> FlowUIDocument:
        payload = self.document.model_dump(mode="python")
        payload["document_id"] = document_id
        payload["revision"] = 1
        payload["template_version"] = self.version
        payload["last_accepted_client_mutation_id"] = None
        return FlowUIDocument.model_validate(payload)


class FlowInterfacePolicy(FlowInterfacePolicySnapshot):
    """Editable policy; frozen into the runtime document on materialization."""


class FlowInterfaceFallbackPolicy(StrictBaseModel):
    unsupported_component: Literal["artifact-card", "json-inspector", "text"] = (
        "artifact-card"
    )
    unsupported_catalog: Literal["ordinary-artifact", "reject"] = "ordinary-artifact"


class FlowInterfaceConfig(StrictBaseModel):
    schema_version: Literal[1] = 1
    template: FlowUIDocumentTemplate
    catalog_id: str = A2UI_PLATFORM_CATALOG_ID
    policy: FlowInterfacePolicy = Field(default_factory=FlowInterfacePolicy)
    submit_action_name: Literal["platform.ui.submit"] = PLATFORM_UI_SUBMIT_ACTION
    fallback_policy: FlowInterfaceFallbackPolicy = Field(
        default_factory=FlowInterfaceFallbackPolicy
    )

    @model_validator(mode="after")
    def validate_template_contract(self) -> FlowInterfaceConfig:
        if self.template.document.catalog_id != self.catalog_id:
            raise ValueError("interface template and config catalog_id must match")
        if (
            self.template.document.policy.model_dump(mode="json")
            != self.policy.model_dump(mode="json")
        ):
            raise ValueError("interface template policy must equal interface policy")
        return self


class FlowInterfaceOverride(StrictBaseModel):
    mode: Literal["inherit", "replace"] = "inherit"
    replacement: FlowInterfaceConfig | None = None

    @model_validator(mode="after")
    def validate_replacement(self) -> FlowInterfaceOverride:
        if self.mode == "replace" and self.replacement is None:
            raise ValueError("interface override mode=replace requires replacement")
        if self.mode == "inherit" and self.replacement is not None:
            raise ValueError("interface override mode=inherit cannot include replacement")
        return self


class EmbedInterfacePolicyOverride(StrictBaseModel):
    show_reasoning: bool | None = None
    tool_calls_display: Literal["hidden", "compact", "detailed"] | None = None
    show_activity: bool | None = None
    show_skill_loads: bool | None = None
    show_reflection: bool | None = None
    errors_display: Literal["generic", "detailed"] | None = None
    show_run_trace: bool | None = None
    show_trace_actions: bool | None = None
    show_browser_previews: bool | None = None
    show_files_panel: bool | None = None
    allow_cancel: bool | None = None
    allow_voice: bool | None = None
    embed_safe_mode: bool | None = None
    initial_page_id: str | None = None


class EmbedInterfaceOverride(StrictBaseModel):
    """Embed-scoped look policy and initial template data, never a second document."""

    policy: EmbedInterfacePolicyOverride = Field(
        default_factory=EmbedInterfacePolicyOverride
    )
    initial_content: JsonObject = Field(default_factory=dict)


def compact_embed_interface_override(
    override: EmbedInterfaceOverride | None,
) -> EmbedInterfaceOverride | None:
    if override is None:
        return None
    policy_payload = override.policy.model_dump(exclude_unset=True, exclude_none=True)
    payload: JsonObject = {}
    if policy_payload:
        payload["policy"] = policy_payload
    if override.initial_content:
        payload["initial_content"] = override.initial_content
    if not payload:
        return None
    return EmbedInterfaceOverride.model_validate(payload)


def apply_embed_interface_override(
    base: FlowInterfaceConfig,
    override: EmbedInterfaceOverride | None,
) -> FlowInterfaceConfig:
    """Apply the embed-only policy/content overlay to one resolved interface.

    The component tree is deliberately immutable here: embed configuration is a
    control-plane overlay, never a second source of UI structure.
    """
    compact = compact_embed_interface_override(override)
    if compact is None:
        return base

    policy_payload = base.policy.model_dump(mode="python")
    policy_payload.update(
        compact.policy.model_dump(exclude_unset=True, exclude_none=True)
    )
    policy = FlowInterfacePolicy.model_validate(policy_payload)
    document = base.template.document.model_copy(
        deep=True,
        update={"policy": policy},
    )

    if compact.initial_content:
        page = document.pages[document.active_page_id]
        surface_id = page.root_surface_id
        surface = document.surfaces[surface_id]
        content = dict(surface.data_model.content)
        content.update(compact.initial_content)
        data_model = surface.data_model.model_copy(update={"content": content})
        surfaces = dict(document.surfaces)
        surfaces[surface_id] = surface.model_copy(update={"data_model": data_model})
        document = document.model_copy(update={"surfaces": surfaces})
    template = base.template.model_copy(update={"document": document})
    return FlowInterfaceConfig.model_validate(
        base.model_copy(update={"policy": policy, "template": template})
    )


def _stack_layout(*, gap: str = "space.4") -> FlowUIContainerLayout:
    return FlowUIContainerLayout(
        mode="stack",
        stack=FlowUIStackDefinition(gap_token=gap),
    )


def build_default_chat_document(
    *,
    policy: FlowInterfacePolicy | None = None,
    greeting_message: str | None = None,
    suggested_prompts: list[str] | None = None,
) -> FlowUIDocument:
    resolved_policy = policy or FlowInterfacePolicy()
    components = {
        "root": FlowUIComponent(
            component_id="root",
            type="PageShell",
            kind="container",
            children=["header", "conversation", "greeting", "suggestions", "message-form"],
            container_layout=FlowUIContainerLayout(
                mode="flex",
                flex=FlowUIFlexDefinition(
                    direction="column",
                    gap_token="space.0",
                ),
            ),
            properties={"presentation": "conversation"},
        ),
        "header": FlowUIComponent(
            component_id="header",
            type="Section",
            kind="container",
            children=["agent-identity", "task-controls"],
            container_layout=FlowUIContainerLayout(
                mode="flex",
                flex=FlowUIFlexDefinition(
                    direction="row",
                    justify_content="space-between",
                ),
            ),
            properties={"presentation": "chat-header"},
        ),
        "agent-identity": FlowUIComponent(
            component_id="agent-identity",
            type="AgentIdentity",
            bindings={"agent": "/system/agent"},
        ),
        "task-controls": FlowUIComponent(
            component_id="task-controls",
            type="TaskControls",
            bindings={"task": "/system/activeTask"},
        ),
        "conversation": FlowUIComponent(
            component_id="conversation",
            type="ConversationFeed",
            kind="container",
            children=["artifact-feed"],
            container_layout=_stack_layout(gap="space.3"),
        ),
        "artifact-feed": FlowUIComponent(
            component_id="artifact-feed",
            type="ArtifactFeed",
            kind="container",
            children=[],
            container_layout=_stack_layout(gap="space.3"),
            bindings={"tasks": "/system/tasks"},
            properties={"presentation": "conversation"},
        ),
        "greeting": FlowUIComponent(
            component_id="greeting",
            type="EmptyState",
            bindings={"message": "/content/greeting"},
        ),
        "suggestions": FlowUIComponent(
            component_id="suggestions",
            type="SuggestedPrompts",
            bindings={"items": "/content/suggestedPrompts", "value": "/values/message"},
            actions={
                "select": FlowUIAction(kind="local", name="values.set")
            },
        ),
        "message-form": FlowUIComponent(
            component_id="message-form",
            type="Form",
            kind="container",
            children=["file-upload", "message-input", "submit"],
            container_layout=_stack_layout(gap="space.3"),
            properties={"formId": "message-form", "presentation": "composer"},
        ),
        "file-upload": FlowUIComponent(
            component_id="file-upload",
            type="FileUpload",
            bindings={"value": "/values/files"},
            properties={"presentation": "composer", "multiple": True},
        ),
        "message-input": FlowUIComponent(
            component_id="message-input",
            type="TextArea",
            bindings={"value": "/values/message"},
            properties={
                "presentation": "composer",
                "rows": 1,
                "placeholder": "Ask anything…",
            },
        ),
        "submit": FlowUIComponent(
            component_id="submit",
            type="Button",
            properties={
                "label": "Send",
                "variant": "primary",
                "presentation": "composer",
            },
            actions={
                "press": FlowUIAction(
                    kind="event",
                    name=PLATFORM_UI_SUBMIT_ACTION,
                    context={"formId": "message-form"},
                )
            },
        ),
    }
    surface = FlowUISurface(
        surface_id="main",
        root_component_id="root",
        components=components,
        data_model=FlowUIDataModel(
            content={
                "greeting": greeting_message or "",
                "suggestedPrompts": list(suggested_prompts or []),
            },
            values={"message": "", "files": []},
            system={"tasks": [], "activeTask": None, "agent": {}},
        ),
    )
    return FlowUIDocument(
        document_id=f"template:{DEFAULT_CHAT_TEMPLATE_ID}:{DEFAULT_CHAT_TEMPLATE_VERSION}",
        template_version=DEFAULT_CHAT_TEMPLATE_VERSION,
        active_page_id="main",
        pages={
            "main": FlowUIPage(
                page_id="main",
                title=LocalizedText(default="Conversation"),
                route="/",
                root_surface_id="main",
            )
        },
        surfaces={"main": surface},
        policy=resolved_policy,
    )


def default_flow_interface_config() -> FlowInterfaceConfig:
    policy = FlowInterfacePolicy()
    document = build_default_chat_document(policy=policy)
    return FlowInterfaceConfig(
        template=FlowUIDocumentTemplate(
            template_id=DEFAULT_CHAT_TEMPLATE_ID,
            version=DEFAULT_CHAT_TEMPLATE_VERSION,
            document=document,
        ),
        policy=policy,
    )


def resolve_interface_override(
    base: FlowInterfaceConfig,
    override: FlowInterfaceOverride | None,
) -> FlowInterfaceConfig:
    if override is None or override.mode == "inherit":
        return base
    if override.replacement is None:
        raise ValueError("replace interface override has no replacement")
    return override.replacement


def resolve_flow_interface_config(
    base: FlowInterfaceConfig,
    *,
    branch_override: FlowInterfaceOverride | None = None,
) -> FlowInterfaceConfig:
    """Resolve the one complete design-time interface for a runtime branch."""
    return resolve_interface_override(base, branch_override)


__all__ = [
    "DEFAULT_CHAT_TEMPLATE_ID",
    "DEFAULT_CHAT_TEMPLATE_VERSION",
    "EmbedInterfacePolicyOverride",
    "EmbedInterfaceOverride",
    "FlowInterfaceConfig",
    "FlowInterfaceFallbackPolicy",
    "FlowInterfaceOverride",
    "FlowInterfacePolicy",
    "FlowUIDocumentTemplate",
    "build_default_chat_document",
    "apply_embed_interface_override",
    "compact_embed_interface_override",
    "default_flow_interface_config",
    "resolve_interface_override",
    "resolve_flow_interface_config",
]
