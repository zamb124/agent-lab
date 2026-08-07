"""One-way data migration from removed chat settings to a Flow UI template."""

from __future__ import annotations

from copy import deepcopy

from core.models.flow_interface import (
    DEFAULT_CHAT_TEMPLATE_ID,
    DEFAULT_CHAT_TEMPLATE_VERSION,
    EmbedInterfaceOverride,
    FlowInterfaceConfig,
    FlowInterfacePolicy,
    FlowUIDocumentTemplate,
    build_default_chat_document,
)
from core.types import JsonObject, require_json_object

_POLICY_FIELDS = frozenset(
    {
        "show_reasoning",
        "tool_calls_display",
        "show_activity",
        "show_skill_loads",
        "show_reflection",
        "errors_display",
        "show_run_trace",
        "show_trace_actions",
        "show_browser_previews",
        "show_files_panel",
        "allow_cancel",
    }
)
_CONTENT_FIELDS = frozenset({"greeting_message", "suggested_prompts"})


def interface_from_removed_chat_settings(raw_chat: JsonObject) -> FlowInterfaceConfig:
    """Build the canonical editable chat template without accepting a runtime alias."""
    unknown = sorted(set(raw_chat) - _POLICY_FIELDS - _CONTENT_FIELDS)
    if unknown:
        raise ValueError(f"Removed chat settings contain unknown fields: {unknown!r}")
    policy = FlowInterfacePolicy.model_validate(
        {key: raw_chat[key] for key in _POLICY_FIELDS if key in raw_chat}
    )
    greeting = raw_chat.get("greeting_message")
    if greeting is not None and not isinstance(greeting, str):
        raise ValueError("chat.greeting_message must be a string or null")
    prompts_raw = raw_chat.get("suggested_prompts", [])
    if not isinstance(prompts_raw, list) or not all(
        isinstance(item, str) for item in prompts_raw
    ):
        raise ValueError("chat.suggested_prompts must be a string array")
    prompts = [item for item in prompts_raw if isinstance(item, str)]
    document = build_default_chat_document(
        policy=policy,
        greeting_message=greeting,
        suggested_prompts=prompts,
    )
    return FlowInterfaceConfig(
        template=FlowUIDocumentTemplate(
            template_id=DEFAULT_CHAT_TEMPLATE_ID,
            version=DEFAULT_CHAT_TEMPLATE_VERSION,
            document=document,
        ),
        policy=policy,
    )


def migrate_flow_config_payload(payload: JsonObject) -> JsonObject:
    """Irreversibly replace one top-level ``chat`` object with ``interface``."""
    migrated = deepcopy(payload)
    raw_chat = migrated.pop("chat", None)
    if raw_chat is None:
        return migrated
    if "interface" in migrated:
        raise ValueError("Flow config contains both removed chat and interface fields")
    chat = require_json_object(raw_chat, "flow.chat")
    interface = interface_from_removed_chat_settings(chat)
    migrated["interface"] = require_json_object(
        interface.model_dump(mode="json", exclude_none=False),
        "FlowInterfaceConfig",
    )
    return migrated


def migrate_embed_config_payload(payload: JsonObject) -> JsonObject:
    """Replace ``chat_override`` with compact policy/initial-content data."""
    migrated = deepcopy(payload)
    if "chat_override" not in migrated:
        return migrated
    raw_override = migrated.pop("chat_override")
    if "interface_override" in migrated:
        raise ValueError("Embed config contains both removed and current override fields")
    if raw_override is None:
        migrated["interface_override"] = None
        return migrated
    override = require_json_object(raw_override, "embed.chat_override")
    unknown = sorted(set(override) - _POLICY_FIELDS - _CONTENT_FIELDS)
    if unknown:
        raise ValueError(f"Embed chat override contains unknown fields: {unknown!r}")
    policy = {
        key: value
        for key, value in override.items()
        if key in _POLICY_FIELDS and value is not None
    }
    initial_content: JsonObject = {}
    greeting = override.get("greeting_message")
    if greeting is not None:
        if not isinstance(greeting, str):
            raise ValueError("embed.chat_override.greeting_message must be a string")
        initial_content["greeting"] = greeting
    if "suggested_prompts" in override and override["suggested_prompts"] is not None:
        prompts = override["suggested_prompts"]
        if not isinstance(prompts, list) or not all(isinstance(item, str) for item in prompts):
            raise ValueError("embed.chat_override.suggested_prompts must be a string array")
        initial_content["suggestedPrompts"] = prompts
    current = EmbedInterfaceOverride.model_validate(
        {"policy": policy, "initial_content": initial_content}
    )
    migrated["interface_override"] = require_json_object(
        current.model_dump(mode="json", exclude_none=True),
        "EmbedInterfaceOverride",
    )
    return migrated


def reconstruct_removed_chat_settings(payload: JsonObject) -> JsonObject:
    """Downgrade only the canonical chat template; custom pages are irreversible."""
    restored = deepcopy(payload)
    raw_interface = restored.pop("interface", None)
    if raw_interface is None:
        return restored
    interface = FlowInterfaceConfig.model_validate(raw_interface)
    if interface.template.template_id != DEFAULT_CHAT_TEMPLATE_ID:
        raise ValueError(
            "Cannot downgrade a custom Flow UI template; restore a pre-migration backup"
        )
    main = interface.template.document.surfaces.get("main")
    if main is None:
        raise ValueError("Cannot downgrade Flow UI without the canonical main surface")
    chat = {
        key: getattr(interface.policy, key)
        for key in _POLICY_FIELDS
    }
    greeting = main.data_model.content.get("greeting")
    prompts = main.data_model.content.get("suggestedPrompts", [])
    chat["greeting_message"] = greeting
    chat["suggested_prompts"] = prompts
    restored["chat"] = chat
    return restored


def reconstruct_removed_embed_override(payload: JsonObject) -> JsonObject:
    restored = deepcopy(payload)
    if "interface_override" not in restored:
        return restored
    raw_override = restored.pop("interface_override")
    if raw_override is None:
        restored["chat_override"] = None
        return restored
    override = EmbedInterfaceOverride.model_validate(raw_override)
    chat = override.policy.model_dump(exclude_unset=True, exclude_none=True)
    if "greeting" in override.initial_content:
        chat["greeting_message"] = override.initial_content["greeting"]
    if "suggestedPrompts" in override.initial_content:
        chat["suggested_prompts"] = override.initial_content["suggestedPrompts"]
    restored["chat_override"] = chat
    return restored


__all__ = [
    "interface_from_removed_chat_settings",
    "migrate_embed_config_payload",
    "migrate_flow_config_payload",
    "reconstruct_removed_chat_settings",
    "reconstruct_removed_embed_override",
]
