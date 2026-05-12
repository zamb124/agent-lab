"""HTML гостевой страницы одноразового preview embed."""

from __future__ import annotations

import html
import json

from core.frontend.viewport import PLATFORM_MOBILE_VIEWPORT_CONTENT

# Нативный ESM: bare `lit` и `@platform/lib/...` задаются import map (как на SPA через бандлер).
_FLOW_PREVIEW_IMPORT_MAP = (
    '<script type="importmap">'
    + json.dumps(
        {
            "imports": {
                "lit": "/static/core/assets/js/lit/lit.min.js",
                "lit/": "/static/core/assets/js/lit/",
                "@platform/lib/": "/static/core/lib/",
            },
        },
        separators=(",", ":"),
    )
    + "</script>"
)

# Как `:root` в `core/frontend/static/assets/css/tokens.css` (тёмная тема) — фон страницы без подключения CSS.
_FLOW_PREVIEW_PAGE_BG = """
html, body { margin: 0; min-height: 100%; }
html[data-theme="dark"], html[data-theme="dark"] body {
  background: linear-gradient(
    135deg,
    #1a1a2e 0%,
    #16213e 25%,
    #0f3460 50%,
    #1a1a2e 75%,
    #16213e 100%
  );
  background-attachment: fixed;
  color-scheme: dark;
}
""".strip()


def _flow_preview_document_lang(interface_locale: str) -> str:
    loc = (interface_locale or "").strip().lower()
    if loc.startswith("en"):
        return "en"
    return "ru"


def build_flow_preview_unavailable_html(*, lang: str, request_id: str | None) -> str:
    if lang not in ("ru", "en"):
        raise ValueError("build_flow_preview_unavailable_html: lang must be ru or en")

    if lang == "en":
        title = "Link unavailable"
        heading = "This page is unavailable"
        body = (
            "This preview link is invalid, was already opened, or has expired. "
            "Ask the sender for a new link."
        )
        ref_caption = "Reference"
    else:
        title = "Ссылка недоступна"
        heading = "Страница недоступна"
        body = (
            "Эта ссылка для просмотра недействительна, уже была открыта или истекла. "
            "Попросите у отправителя новую ссылку."
        )
        ref_caption = "Идентификатор запроса"

    ref_html = ""
    if isinstance(request_id, str) and request_id.strip():
        safe_ref = html.escape(request_id.strip(), quote=True)
        ref_html = (
            f'<p class="ref">{html.escape(ref_caption, quote=True)}: '
            f"<code>{safe_ref}</code></p>"
        )

    return f"""<!DOCTYPE html>
<html lang="{html.escape(lang, quote=True)}" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="{PLATFORM_MOBILE_VIEWPORT_CONTENT}">
  <meta name="robots" content="noindex, nofollow">
  <title>{html.escape(title, quote=True)}</title>
  <style>
{_FLOW_PREVIEW_PAGE_BG}
    body {{ font-family: system-ui, sans-serif; margin: 2rem; line-height: 1.5; color: #e8eaed; }}
    h1 {{ font-size: 1.25rem; font-weight: 600; margin: 0 0 0.75rem; }}
    p {{ margin: 0 0 1rem; max-width: 36rem; }}
    .ref {{ font-size: 0.85rem; opacity: 0.75; margin-top: 2rem; }}
    code {{ font-family: ui-monospace, monospace; }}
  </style>
</head>
<body>
  <h1>{html.escape(heading, quote=True)}</h1>
  <p>{html.escape(body, quote=True)}</p>
  {ref_html}
</body>
</html>"""


def build_flow_preview_guest_html(
    *,
    script_url: str,
    embed_id: str,
    flow_id: str,
    branch_id: str,
    assistant_title: str,
    interface_locale: str,
    flows_base_url: str,
    platform_ui_origin: str,
    static_bearer: str,
    company_id: str,
) -> str:
    doc_lang = _flow_preview_document_lang(interface_locale)
    # Гостевой preview всегда в тёмной теме платформы; панель открыта с первого кадра.
    guest_theme = "dark"
    open_attrs = [
        f'src="{html.escape(script_url, quote=True)}"',
        f'data-embed-id="{html.escape(embed_id, quote=True)}"',
        f'data-flow-id="{html.escape(flow_id, quote=True)}"',
        f'data-branch-id="{html.escape(branch_id, quote=True)}"',
        f'data-assistant-title="{html.escape(assistant_title, quote=True)}"',
        f'data-theme="{html.escape(guest_theme, quote=True)}"',
        f'data-locale="{html.escape(interface_locale, quote=True)}"',
        'data-initial-open="true"',
        'data-show-launcher="true"',
        f'data-flows-base-url="{html.escape(flows_base_url, quote=True)}"',
        f'data-platform-ui-origin="{html.escape(platform_ui_origin, quote=True)}"',
        'data-chat-token-url="/flow-preview/unused"',
        'data-token-expires-seconds="86400"',
        'data-use-credentials="false"',
        'data-event-namespace="assistant"',
        'data-toggle-event-name="humanitec-embed-chat-toggle"',
        'data-voice-enabled="false"',
        'data-voice-default-on="false"',
        f'data-company-id="{html.escape(company_id, quote=True)}"',
        f'data-static-bearer="{html.escape(static_bearer, quote=True)}"',
    ]
    attrs = "\n  ".join(open_attrs)
    safe_title = html.escape(assistant_title, quote=True)
    safe_lang = html.escape(doc_lang, quote=True)
    return f"""<!DOCTYPE html>
<html lang="{safe_lang}" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="{PLATFORM_MOBILE_VIEWPORT_CONTENT}">
  <meta name="robots" content="noindex, nofollow">
  <title>{safe_title}</title>
  <style>{_FLOW_PREVIEW_PAGE_BG}</style>
  {_FLOW_PREVIEW_IMPORT_MAP}
</head>
<body>
<script type="module"
  {attrs}
></script>
</body>
</html>"""
