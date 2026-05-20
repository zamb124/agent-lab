"""
Минимальная HTML-страница ошибок доступа к компании по Host/subdomain (без SPA).
Тема: localStorage platform_theme, иначе prefers-color-scheme, иначе dark.
"""

import html
from datetime import datetime, timezone

from fastapi.responses import HTMLResponse


def build_company_access_error_html(
    status_code: int,
    message: str,
) -> str:
    """message — отображаемый текст, уже безопасно не считаем (экранируем)."""
    safe_message = html.escape(message, quote=True)
    year = datetime.now(timezone.utc).year
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Доступ ограничен</title>
  <script>
  (function() {{
    var t = null;
    try {{ t = localStorage.getItem('platform_theme'); }} catch (e) {{}}
    var m;
    if (t === 'light' || t === 'dark') {{
      m = t;
    }} else if (window.matchMedia('(prefers-color-scheme: light)').matches) {{
      m = 'light';
    }} else {{
      m = 'dark';
    }}
    if (m !== 'light' && m !== 'dark') m = 'dark';
    document.documentElement.setAttribute('data-theme', m);
  }})();
  </script>
  <style>
  :root, [data-theme="dark"] {{
    --page-bg: #0a0a0c;
    --page-text: #e8e8ef;
    --page-muted: #9a9aaa;
  }}
  [data-theme="light"] {{
    --page-bg: #f5f5f7;
    --page-text: #1a1a1e;
    --page-muted: #5a5a66;
  }}
  body {{
    margin: 0;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
    background: var(--page-bg);
    color: var(--page-text);
  }}
  .box {{
    max-width: 28rem;
    padding: 1.5rem 1.25rem;
    line-height: 1.5;
  }}
  .code {{
    font-size: 0.75rem;
    color: var(--page-muted);
    margin-bottom: 0.75rem;
  }}
  p {{ margin: 0 0 0.5rem; }}
  .en {{ margin-top: 1rem; font-size: 0.9rem; color: var(--page-muted); }}
  .footer {{ margin-top: 2rem; font-size: 0.7rem; color: var(--page-muted); }}
  </style>
</head>
<body>
  <div class="box">
    <div class="code">HTTP {status_code}</div>
    <p>{safe_message}</p>
    <p class="en">If you need access, ask your organization administrator. / Если нужен доступ, обратитесь к администратору организации.</p>
    <p class="footer">Humanitec &middot; {year}</p>
  </div>
</body>
</html>
"""


def build_company_access_error_response(
    status_code: int,
    message: str,
) -> HTMLResponse:
    return HTMLResponse(
        content=build_company_access_error_html(status_code, message),
        status_code=status_code,
    )


def http_exception_detail_to_str(detail) -> str:
    if isinstance(detail, str):
        return detail
    return str(detail)
