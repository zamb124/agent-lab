from pathlib import Path


def test_platform_chat_uses_action_invoked_without_legacy_fallbacks() -> None:
    chat_path = Path("core/frontend/static/lib/chat/platform-chat.js")
    source = chat_path.read_text(encoding="utf-8")

    assert "_injectActionBlocksFromUiEvents" not in source
    assert "assistant_event_type" not in source
    assert "assistant:action_apply" not in source
    assert "action_invoked" in source
