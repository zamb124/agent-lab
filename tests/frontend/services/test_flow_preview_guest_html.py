from apps.frontend.services.flow_preview_guest_html import build_flow_preview_guest_html


def test_guest_html_uses_static_bearer_without_token_url() -> None:
    html = build_flow_preview_guest_html(
        script_url="https://api.example/static/core/lib/embed-flow-ui/flow-ui-embed-autoload.js",
        embed_id="emb_preview",
        flow_id="flow_preview",
        branch_id="default",
        assistant_title="Preview",
        interface_locale="ru",
        flows_base_url="https://api.example/flows",
        platform_ui_origin="https://api.example",
        static_bearer="guest-token",
        company_id="co_preview",
    )
    assert 'data-static-bearer="guest-token"' in html
    assert "data-token-url" not in html
    assert "/flow-preview/unused" not in html
    assert 'data-presentation="page"' in html
    assert 'data-toggle-event-name="linnex-flow-ui-toggle"' in html
