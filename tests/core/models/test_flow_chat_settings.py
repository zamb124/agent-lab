"""Unit-тесты merge effective chat policy: FlowConfig.chat + EmbedChatPolicyOverride."""

from core.models.flow_chat_settings import (
    EmbedChatPolicyOverride,
    FlowChatSettings,
    resolve_effective_flow_chat,
)


def test_resolve_effective_flow_chat_without_override_returns_flow() -> None:
    flow_chat = FlowChatSettings(
        show_reasoning=True,
        tool_calls_display="detailed",
        greeting_message="Hello flow",
        suggested_prompts=["A", "B"],
    )
    effective = resolve_effective_flow_chat(flow_chat, None)
    assert effective == flow_chat


def test_resolve_effective_flow_chat_partial_override() -> None:
    flow_chat = FlowChatSettings(
        show_reasoning=False,
        tool_calls_display="compact",
        errors_display="generic",
        show_files_panel=True,
        greeting_message="Flow greeting",
        suggested_prompts=["Flow prompt"],
    )
    override = EmbedChatPolicyOverride(
        show_reasoning=True,
        tool_calls_display="hidden",
        show_files_panel=False,
        greeting_message=None,
    )
    effective = resolve_effective_flow_chat(flow_chat, override)
    assert effective.show_reasoning is True
    assert effective.tool_calls_display == "hidden"
    assert effective.errors_display == "generic"
    assert effective.show_files_panel is False
    assert effective.greeting_message is None
    assert effective.suggested_prompts == ["Flow prompt"]


def test_resolve_effective_flow_chat_empty_override_object_is_noop() -> None:
    flow_chat = FlowChatSettings(show_activity=False, show_skill_loads=False)
    override = EmbedChatPolicyOverride()
    effective = resolve_effective_flow_chat(flow_chat, override)
    assert effective.show_activity is False
    assert effective.show_skill_loads is False


def test_resolve_effective_flow_chat_override_show_skill_loads() -> None:
    flow_chat = FlowChatSettings(show_skill_loads=True)
    override = EmbedChatPolicyOverride(show_skill_loads=False)
    effective = resolve_effective_flow_chat(flow_chat, override)
    assert effective.show_skill_loads is False


def test_resolve_effective_flow_chat_override_show_reflection() -> None:
    flow_chat = FlowChatSettings(show_reflection=True)
    override = EmbedChatPolicyOverride(show_reflection=False)
    effective = resolve_effective_flow_chat(flow_chat, override)
    assert effective.show_reflection is False


def test_resolve_effective_flow_chat_override_suggested_prompts() -> None:
    flow_chat = FlowChatSettings(suggested_prompts=["one"])
    override = EmbedChatPolicyOverride(suggested_prompts=[])
    effective = resolve_effective_flow_chat(flow_chat, override)
    assert effective.suggested_prompts == []
