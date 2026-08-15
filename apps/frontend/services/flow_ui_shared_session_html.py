"""Minimal first-party host for a scoped live Flow UI shared session."""

from __future__ import annotations

import html
import json

from core.frontend.viewport import PLATFORM_MOBILE_VIEWPORT_CONTENT

# Same key as core/frontend/static/lib/events/effects/theme.effect.js
_PLATFORM_THEME_STORAGE_KEY = "platform_theme"


def build_flow_ui_shared_session_html(*, grant_id: str) -> str:
    safe_grant = json.dumps(grant_id, ensure_ascii=False)
    safe_theme_key = json.dumps(_PLATFORM_THEME_STORAGE_KEY, ensure_ascii=False)
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
<html lang="ru" data-theme="light">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="{viewport}">
  <meta name="theme-color" content="#ffffff">
  <meta name="robots" content="noindex,nofollow,noarchive">
  <title>Shared Flow UI · Linnex</title>
  <script type="importmap">{import_map}</script>
  <link rel="stylesheet" href="/static/core/assets/css/tokens.css">
  <style>
    * {{ box-sizing: border-box; }}
    html, body {{
      margin: 0;
      min-height: 100%;
      background: var(--flow-ui-page-background, var(--bg-primary, #f8fafc));
      color: var(--text-primary, #1c1f2e);
      color-scheme: light dark;
    }}
    body {{ min-height: 100dvh; font-family: var(--font-sans, Inter, ui-sans-serif, system-ui, sans-serif); }}
    main {{
      position: relative;
      min-height: 100dvh;
      display: grid;
      place-items: stretch;
      padding: clamp(0px, 2vw, 24px);
    }}
    platform-flow-ui {{
      min-height: calc(100dvh - clamp(0px, 4vw, 48px));
      border-radius: 24px;
      overflow: hidden;
      border: 1px solid var(--flow-ui-border, var(--border-default, rgba(28, 31, 46, 0.1)));
      box-shadow: var(--flow-ui-panel-shadow, var(--glass-shadow-medium));
    }}
    .state {{ min-height: 100dvh; display: grid; place-items: center; padding: 24px; text-align: center; }}
    .state > div {{
      max-width: 520px;
      padding: 24px;
      border: 1px solid var(--flow-ui-border, var(--border-default, rgba(160, 177, 210, 0.18)));
      border-radius: 22px;
      background: var(--flow-ui-panel-strong, var(--glass-solid-strong, var(--bg-elevated)));
      box-shadow: var(--flow-ui-panel-shadow, var(--glass-shadow-medium));
    }}
    .state p {{ color: var(--flow-ui-muted, var(--text-tertiary)); line-height: 1.6; }}
    .theme-toggle {{
      position: fixed;
      top: max(12px, env(safe-area-inset-top, 0px));
      right: max(12px, env(safe-area-inset-right, 0px));
      z-index: 40;
      width: 40px;
      height: 40px;
      padding: 0;
      border-radius: 50%;
      display: inline-grid;
      place-items: center;
      cursor: pointer;
      border: 1px solid var(--flow-ui-border, var(--border-default));
      background: var(--flow-ui-panel-strong, var(--glass-solid-strong, var(--bg-elevated)));
      color: var(--flow-ui-text, var(--text-primary));
      box-shadow: var(--flow-ui-panel-shadow, var(--glass-shadow-medium));
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
    }}
    .theme-toggle:hover {{
      border-color: color-mix(in srgb, var(--accent, #6d62e8) 45%, var(--flow-ui-border, transparent));
    }}
    .theme-toggle img {{
      width: 18px;
      height: 18px;
      display: block;
      filter: brightness(0) opacity(0.72);
    }}
    html[data-theme="dark"] .theme-toggle img {{
      filter: brightness(0) saturate(100%) invert(88%) opacity(0.92);
    }}
  </style>
  <script>
    (() => {{
      const STORAGE_KEY = {safe_theme_key};
      const meta = () => document.querySelector('meta[name="theme-color"]');
      const applyTheme = (mode) => {{
        if (mode !== 'light' && mode !== 'dark') {{
          throw new Error(`share host: unsupported theme ${{JSON.stringify(mode)}}`);
        }}
        document.documentElement.setAttribute('data-theme', mode);
        const themeMeta = meta();
        if (themeMeta) themeMeta.setAttribute('content', mode === 'dark' ? '#0a0a0c' : '#ffffff');
        const toggle = document.getElementById('theme-toggle');
        if (toggle instanceof HTMLButtonElement) {{
          const next = mode === 'dark' ? 'light' : 'dark';
          const label = mode === 'dark' ? 'Включить светлую тему' : 'Включить тёмную тему';
          toggle.setAttribute('aria-label', label);
          toggle.title = label;
          const icon = toggle.querySelector('img');
          if (icon instanceof HTMLImageElement) {{
            icon.src = next === 'light'
              ? '/static/core/assets/icons/sun.svg'
              : '/static/core/assets/icons/moon.svg';
          }}
        }}
      }};
      const stored = localStorage.getItem(STORAGE_KEY);
      let initial = 'light';
      if (stored === 'light' || stored === 'dark') {{
        initial = stored;
      }} else if (window.matchMedia('(prefers-color-scheme: dark)').matches) {{
        initial = 'dark';
      }}
      applyTheme(initial);
      window.__flowUiShareTheme = {{
        get: () => document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light',
        set: (mode) => {{
          applyTheme(mode);
          localStorage.setItem(STORAGE_KEY, mode);
        }},
        toggle: () => {{
          const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
          window.__flowUiShareTheme.set(next);
        }},
      }};
    }})();
  </script>
</head>
<body>
  <button type="button" class="theme-toggle" id="theme-toggle" aria-label="Включить тёмную тему" title="Включить тёмную тему">
    <img src="/static/core/assets/icons/moon.svg" alt="" aria-hidden="true">
  </button>
  <main id="app"><div class="state"><div><strong>Открываем сохранённый экран…</strong><p>Загружается последняя подтверждённая ревизия этой сессии.</p></div></div></main>
  <script type="module">
    import '/static/core/lib/flow-ui/components/platform-flow-ui.js';
    const grantId = {safe_grant};
    const app = document.querySelector('#app');
    const themeToggle = document.getElementById('theme-toggle');
    if (!(themeToggle instanceof HTMLButtonElement)) {{
      throw new Error('share host: theme toggle missing');
    }}
    themeToggle.addEventListener('click', () => window.__flowUiShareTheme.toggle());
    // Re-apply after DOM ready so the toggle icon matches the bootstrapped theme.
    window.__flowUiShareTheme.set(window.__flowUiShareTheme.get());
    let session = null;
    let surface = null;
    let refreshTimer = null;
    const fail = (message) => {{
      if (refreshTimer !== null) clearTimeout(refreshTimer);
      app.innerHTML = '<div class="state"><div><strong>Ссылка недоступна</strong><p></p></div></div>';
      const detail = app.querySelector('p');
      if (!(detail instanceof HTMLElement)) throw new Error('share host: fail detail node missing');
      detail.textContent = message;
    }};
    const exchange = async () => {{
      const response = await fetch(`/flows/api/v1/flow-ui/shares/exchange/${{encodeURIComponent(grantId)}}`, {{
        method: 'POST', headers: {{ Accept: 'application/json' }}, credentials: 'omit',
      }});
      if (!response.ok) {{
        throw new Error(response.status === 404 ? 'Ссылка истекла или была отозвана.' : `HTTP ${{response.status}}`);
      }}
      session = await response.json();
      if (typeof session.flows_base_url !== 'string' || session.flows_base_url.trim() === '') {{
        throw new Error('share exchange: flows_base_url required');
      }}
      if (typeof session.token !== 'string' || session.token.trim() === '') {{
        throw new Error('share exchange: token required');
      }}
      if (typeof session.token_type !== 'string' || session.token_type.trim() === '') {{
        throw new Error('share exchange: token_type required');
      }}
      if (typeof session.expires_at !== 'string' || session.expires_at.trim() === '') {{
        throw new Error('share exchange: expires_at required');
      }}
      const remaining = Math.max(0, Date.parse(session.expires_at) - Date.now());
      if (!Number.isFinite(remaining)) {{
        throw new Error('share exchange: expires_at is not a valid timestamp');
      }}
      const refreshIn = Math.max(1000, Math.min(remaining * .8, remaining - 30_000));
      if (refreshTimer !== null) clearTimeout(refreshTimer);
      refreshTimer = setTimeout(async () => {{
        try {{ await exchange(); }}
        catch (error) {{
          fail(error instanceof Error ? error.message : 'Ссылка больше недоступна.');
        }}
      }}, refreshIn);
      return session;
    }};
    try {{
      await exchange();
      surface = document.createElement('platform-flow-ui');
      surface.flowId = session.flow_id;
      surface.branchId = session.branch_id;
      surface.contextId = session.context_id;
      surface.baseUrl = session.flows_base_url;
      surface.display = 'page';
      surface.profile = 'shared_session';
      surface.theme = 'auto';
      surface.credentials = 'omit';
      surface.readonly = session.permission !== 'editor';
      surface.getRequestHeaders = () => ({{ Authorization: `${{session.token_type}} ${{session.token}}` }});
      surface.addEventListener('flow-ui-error', (event) => {{
        const message = event.detail?.error?.message;
        fail(typeof message === 'string' && message ? message : 'Не удалось восстановить экран.');
      }});
      app.replaceChildren(surface);
    }} catch (error) {{
      fail(error instanceof Error ? error.message : 'Не удалось открыть ссылку.');
    }}
  </script>
</body>
</html>"""


__all__ = ["build_flow_ui_shared_session_html"]
