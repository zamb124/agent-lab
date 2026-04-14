from pathlib import Path


def test_embed_chat_drawer_nonmodal_without_outside_close() -> None:
    drawer_path = Path("core/frontend/static/lib/embed-chat/platform-embed-chat-drawer.js")
    source = drawer_path.read_text(encoding="utf-8")

    assert "class=\"backdrop" not in source
    assert "backdrop--hidden" not in source
    assert "@click=${this._close}" not in source
    assert "_close()" not in source
    assert "_minimize()" in source
    assert "@click=${this._minimize}" in source


def test_embed_chat_drawer_uses_minimize_label() -> None:
    labels_path = Path("core/frontend/static/lib/embed-chat/embed-chat-default-labels.js")
    labels = labels_path.read_text(encoding="utf-8")

    assert "panel_minimize" in labels
