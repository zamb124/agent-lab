from pathlib import Path


def test_legacy_embed_files_removed() -> None:
    root = Path(__file__).resolve().parents[2]
    assert not (root / "apps/flows/src/api/embed.py").exists()
    assert not (root / "apps/flows/ui/embed/chat-widget.js").exists()
    assert not (root / "core/frontend/static/embed/chat-widget.js").exists()


def test_no_legacy_widget_snippet_in_embed_configs_api() -> None:
    root = Path(__file__).resolve().parents[2]
    content = (root / "apps/frontend/api/embed_configs.py").read_text(encoding="utf-8")
    assert "new HumanitecChat" not in content
    assert "chat-widget.min.js" not in content


def test_no_legacy_embed_route_rule() -> None:
    root = Path(__file__).resolve().parents[2]
    route_config = (root / "core/middleware/auth/route_config.py").read_text(encoding="utf-8")
    assert "/flows/api/v1/embed/*" not in route_config
