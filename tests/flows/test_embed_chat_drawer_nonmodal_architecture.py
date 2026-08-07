from pathlib import Path


def test_flow_ui_drawer_nonmodal_without_outside_close() -> None:
    drawer_path = Path("core/frontend/static/lib/flow-ui/shell/drawer.js")
    source = drawer_path.read_text(encoding="utf-8")

    assert 'class="backdrop' not in source
    assert "backdrop--hidden" not in source
    assert "class=\"launcher\"" in source or "class='launcher'" in source or "class=\"launcher\"" in source.replace("'", '"')
    assert "FLOW_UI_TOGGLE_EVENT" in source
    assert "platform-flow-ui" in source
