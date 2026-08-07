"""Hard-cut миграция удалённых chat-настроек в единственный Flow UI template."""

import pytest

from core.a2a.extensions import PLATFORM_UI_SUBMIT_ACTION
from core.models.flow_interface import (
    DEFAULT_CHAT_TEMPLATE_ID,
    DEFAULT_CHAT_TEMPLATE_VERSION,
    EmbedInterfaceOverride,
    FlowInterfaceConfig,
    FlowInterfacePolicy,
    FlowUIDocumentTemplate,
    apply_embed_interface_override,
    build_default_chat_document,
    default_flow_interface_config,
)
from core.models.flow_interface_migration import (
    interface_from_removed_chat_settings,
    migrate_embed_config_payload,
    migrate_flow_config_payload,
    reconstruct_removed_chat_settings,
    reconstruct_removed_embed_override,
)

REMOVED_POLICY_FIELDS = (
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
)


def _submit_component_ids(interface: FlowInterfaceConfig) -> list[str]:
    return sorted(
        component.component_id
        for surface in interface.template.document.surfaces.values()
        for component in surface.components.values()
        for action in component.actions.values()
        if action.name == PLATFORM_UI_SUBMIT_ACTION
    )


def test_removed_chat_settings_become_policy_and_template_content() -> None:
    interface = interface_from_removed_chat_settings(
        {
            "show_reasoning": True,
            "tool_calls_display": "detailed",
            "errors_display": "detailed",
            "show_files_panel": False,
            "greeting_message": "Привет из настроек",
            "suggested_prompts": ["Что ты умеешь?", "Покажи отчёт"],
        }
    )

    assert interface.template.template_id == DEFAULT_CHAT_TEMPLATE_ID
    assert interface.policy.show_reasoning is True
    assert interface.policy.tool_calls_display == "detailed"
    assert interface.policy.errors_display == "detailed"
    assert interface.policy.show_files_panel is False
    assert interface.policy.show_activity is True

    main = interface.template.document.surfaces["main"]
    assert main.data_model.content["greeting"] == "Привет из настроек"
    assert main.data_model.content["suggestedPrompts"] == [
        "Что ты умеешь?",
        "Покажи отчёт",
    ]
    assert _submit_component_ids(interface) == ["submit"]
    assert interface.template.document.policy.model_dump(
        mode="json"
    ) == interface.policy.model_dump(mode="json")


def test_flow_config_migration_replaces_chat_with_interface() -> None:
    migrated = migrate_flow_config_payload(
        {
            "flow_id": "support",
            "name": "Support",
            "chat": {"show_reasoning": True, "greeting_message": "Hello"},
        }
    )

    assert "chat" not in migrated
    assert migrated["flow_id"] == "support"
    interface = FlowInterfaceConfig.model_validate(migrated["interface"])
    assert interface.policy.show_reasoning is True
    assert (
        interface.template.document.surfaces["main"].data_model.content["greeting"]
        == "Hello"
    )


def test_flow_config_without_removed_chat_is_untouched() -> None:
    payload = {"flow_id": "support", "interface": None}
    assert migrate_flow_config_payload(payload) == payload


def test_flow_config_with_both_contracts_fails_closed() -> None:
    with pytest.raises(ValueError, match="both removed chat and interface"):
        migrate_flow_config_payload(
            {"chat": {"show_reasoning": True}, "interface": {"schema_version": 1}}
        )


def test_unknown_removed_chat_field_stops_migration() -> None:
    with pytest.raises(ValueError, match="unknown fields"):
        interface_from_removed_chat_settings({"show_reasoning": True, "show_avatar": True})


def test_malformed_removed_chat_content_stops_migration() -> None:
    with pytest.raises(ValueError, match="greeting_message"):
        interface_from_removed_chat_settings({"greeting_message": 42})
    with pytest.raises(ValueError, match="suggested_prompts"):
        interface_from_removed_chat_settings({"suggested_prompts": "single"})


def test_embed_chat_override_keeps_explicit_false_and_empty_values() -> None:
    migrated = migrate_embed_config_payload(
        {
            "embed_id": "e1",
            "chat_override": {
                "show_reasoning": True,
                "tool_calls_display": "hidden",
                "show_files_panel": False,
                "greeting_message": "Embed greeting",
                "suggested_prompts": [],
            },
        }
    )

    assert "chat_override" not in migrated
    override = EmbedInterfaceOverride.model_validate(migrated["interface_override"])
    assert override.policy.show_reasoning is True
    assert override.policy.tool_calls_display == "hidden"
    assert override.policy.show_files_panel is False
    assert override.policy.allow_cancel is None
    assert override.initial_content == {
        "greeting": "Embed greeting",
        "suggestedPrompts": [],
    }


def test_embed_override_null_stays_null_and_unknown_field_fails() -> None:
    migrated = migrate_embed_config_payload({"embed_id": "e1", "chat_override": None})
    assert migrated["interface_override"] is None

    with pytest.raises(ValueError, match="unknown fields"):
        migrate_embed_config_payload({"chat_override": {"show_avatar": True}})


def test_embed_override_downgrade_restores_only_explicit_fields() -> None:
    migrated = migrate_embed_config_payload(
        {"chat_override": {"show_reasoning": True, "suggested_prompts": ["one"]}}
    )
    restored = reconstruct_removed_embed_override(migrated)

    assert "interface_override" not in restored
    assert restored["chat_override"] == {
        "show_reasoning": True,
        "suggested_prompts": ["one"],
    }


def test_default_chat_template_downgrade_restores_full_policy() -> None:
    migrated = migrate_flow_config_payload(
        {"chat": {"show_run_trace": True, "greeting_message": "Hi", "suggested_prompts": ["a"]}}
    )
    restored = reconstruct_removed_chat_settings(migrated)

    assert "interface" not in restored
    chat = restored["chat"]
    assert set(chat) == {*REMOVED_POLICY_FIELDS, "greeting_message", "suggested_prompts"}
    assert chat["show_run_trace"] is True
    assert chat["greeting_message"] == "Hi"
    assert chat["suggested_prompts"] == ["a"]


def test_custom_template_downgrade_is_refused() -> None:
    policy = FlowInterfacePolicy()
    custom = FlowInterfaceConfig(
        template=FlowUIDocumentTemplate(
            template_id="acme.custom-portal",
            version="2.0.0",
            document=build_default_chat_document(policy=policy),
        ),
        policy=policy,
    )
    payload = {"interface": custom.model_dump(mode="json")}

    with pytest.raises(ValueError, match="custom Flow UI template"):
        reconstruct_removed_chat_settings(payload)


def test_embed_override_overlays_policy_without_second_document() -> None:
    base = default_flow_interface_config()
    override = EmbedInterfaceOverride.model_validate(
        {
            "policy": {"show_reasoning": True, "allow_cancel": False},
            "initial_content": {"greeting": "Embed hello"},
        }
    )

    applied = apply_embed_interface_override(base, override)

    assert applied.policy.show_reasoning is True
    assert applied.policy.allow_cancel is False
    assert applied.policy.errors_display == base.policy.errors_display
    assert applied.template.template_id == base.template.template_id
    assert applied.template.version == DEFAULT_CHAT_TEMPLATE_VERSION
    assert (
        applied.template.document.surfaces["main"].components.keys()
        == base.template.document.surfaces["main"].components.keys()
    )
    assert (
        applied.template.document.surfaces["main"].data_model.content["greeting"]
        == "Embed hello"
    )
    assert applied.template.document.policy.model_dump(
        mode="json"
    ) == applied.policy.model_dump(mode="json")


def test_embed_override_without_explicit_fields_returns_same_interface() -> None:
    base = default_flow_interface_config()
    assert apply_embed_interface_override(base, EmbedInterfaceOverride()) is base
    assert apply_embed_interface_override(base, None) is base
