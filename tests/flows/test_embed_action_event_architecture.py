from pathlib import Path


def test_platform_flow_ui_submit_action_is_canonical() -> None:
    constants_path = Path("core/frontend/static/lib/flow-ui/protocol/constants.js")
    source = constants_path.read_text(encoding="utf-8")
    assert "platform.ui.submit" in source
    assert "assistant:action_apply" not in source
    assert "_injectActionBlocksFromUiEvents" not in source
