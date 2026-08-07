"""First-party HTML host for EmbedConfig.presentation=page."""

from __future__ import annotations

import html
import json

from core.frontend.viewport import PLATFORM_MOBILE_VIEWPORT_CONTENT


def build_flow_embed_page_html(*, embed_id: str) -> str:
    safe_embed = json.dumps(embed_id, ensure_ascii=False)
    import_map = json.dumps(
        {
            "imports": {
                "lit": "/static/core/assets/js/lit/lit.min.js",
                "lit/": "/static/core/assets/js/lit/",
                "@platform/lib/": "/static/core/lib/",
            }
        },
        separators=(",", ":"),
    )
    viewport = html.escape(PLATFORM_MOBILE_VIEWPORT_CONTENT, quote=True)
    return f"""<!doctype html>
<html lang="ru" data-theme="dark">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="{viewport}">
  <meta name="robots" content="noindex,nofollow,noarchive">
  <title>Flow UI · Linnex</title>
  <script type="importmap">{import_map}</script>
  <link rel="stylesheet" href="/static/core/assets/css/tokens.css">
  <link rel="stylesheet" href="/static/core/lib/flow-ui/shell/tokens.css">
  <style>
    * {{ box-sizing: border-box; }}
    html, body {{
      margin: 0;
      min-height: 100%;
      background: var(--flow-ui-page-background, var(--bg-primary, #16213e));
      color: var(--text-primary, #eaf0fb);
    }}
    body {{ min-height: 100dvh; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }}
    #app {{ min-height: 100dvh; display: block; }}
    flow-ui-page-host, platform-flow-ui {{ display: block; width: 100%; height: 100dvh; min-height: 100dvh; }}
    .state {{ min-height: 100dvh; display: grid; place-items: center; padding: 24px; text-align: center; }}
    .state > div {{
      max-width: 520px; padding: 24px;
      border: 1px solid rgba(160,177,210,.18); border-radius: 22px;
      background: rgba(19,28,48,.8);
    }}
    .state p {{ color: #9cabc4; line-height: 1.6; }}
  </style>
</head>
<body>
  <div id="app"><div class="state"><div><strong>Открываем Flow UI…</strong><p>Загружается полноэкранная страница.</p></div></div></div>
  <script type="module">
    import '/static/core/lib/flow-ui/shell/page-host.js';
    const embedId = {safe_embed};
    const app = document.querySelector('#app');
    const fail = (message) => {{
      app.innerHTML = '<div class="state"><div><strong>Страница недоступна</strong><p></p></div></div>';
      const detail = app.querySelector('p');
      if (!(detail instanceof HTMLElement)) throw new Error('embed page host: fail detail missing');
      detail.textContent = message;
    }};
    try {{
      const origin = globalThis.location.origin;
      const response = await fetch(
        `/frontend/api/public/embed-page/session`,
        {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json', Accept: 'application/json' }},
          credentials: 'omit',
          body: JSON.stringify({{ embed_id: embedId, origin }}),
        }},
      );
      if (!response.ok) {{
        throw new Error(
          response.status === 404
            ? 'Виджет не найден или отключён.'
            : response.status === 403
              ? 'Полноэкранная страница для этого виджета недоступна.'
              : `HTTP ${{response.status}}`,
        );
      }}
      const session = await response.json();
      if (typeof session.token !== 'string' || session.token.trim() === '') {{
        throw new Error('embed page session: token required');
      }}
      if (typeof session.flows_base_url !== 'string' || session.flows_base_url.trim() === '') {{
        throw new Error('embed page session: flows_base_url required');
      }}
      if (typeof session.flow_id !== 'string' || session.flow_id.trim() === '') {{
        throw new Error('embed page session: flow_id required');
      }}
      const host = document.createElement('flow-ui-page-host');
      host.config = {{
        embedId,
        flowId: session.flow_id,
        branchId: typeof session.branch_id === 'string' ? session.branch_id : 'default',
        baseUrl: session.flows_base_url,
        theme: typeof session.theme === 'string' ? session.theme : 'dark',
        locale: typeof session.interface_locale === 'string' ? session.interface_locale : 'auto',
        profile: 'embed_public',
        getRequestHeaders: () => ({{ Authorization: `Bearer ${{session.token}}` }}),
      }};
      app.replaceChildren(host);
    }} catch (error) {{
      fail(error instanceof Error ? error.message : 'Не удалось открыть страницу.');
    }}
  </script>
</body>
</html>"""


__all__ = ["build_flow_embed_page_html"]
