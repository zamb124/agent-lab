"""
HTML для ошибок универсального OAuth callback (навигация браузера, Sec-Fetch-Dest: document).
"""

from __future__ import annotations

import html as html_module

from starlette.requests import Request

from core.integrations.guided_integration_error import (
    GuidedIntegrationError,
    OAuthErrorLocale,
)


def oauth_callback_prefers_html_response(request: Request) -> bool:
    """
    Top-level браузерный переход на callback — Sec-Fetch-Dest: document.
    Программные клиенты (pytest, curl без Fetch Metadata) чаще без этого заголовка; им — JSON.
    """
    raw = request.headers.get("sec-fetch-dest")
    return isinstance(raw, str) and raw.strip().lower() == "document"


def resolve_oauth_integration_locale(accept_language: str | None) -> OAuthErrorLocale:
    """Первый подходящий тег Accept-Language: en-* → en, иначе ru."""
    if not isinstance(accept_language, str) or not accept_language.strip():
        return "ru"
    for part in accept_language.split(","):
        tag_raw = part.split(";")[0].strip().lower()
        if not tag_raw:
            continue
        primary = tag_raw.split("-", 1)[0]
        if primary == "en":
            return "en"
        return "ru"
    return "ru"


def build_integration_oauth_error_html(
    exc: GuidedIntegrationError,
    *,
    locale: OAuthErrorLocale,
    correlation: dict[str, str] | None = None,
) -> str:
    title = html_module.escape(exc.title_for_locale(locale))
    message = html_module.escape(exc.message_for_locale(locale))
    steps = [
        html_module.escape(step) for step in exc.steps_for_locale(locale)
    ]
    corr_id = correlation or {}

    buttons: list[str] = []
    for link in exc.links:
        href = html_module.escape(link.href, quote=True)
        label = html_module.escape(
            link.label_en if locale == "en" else link.label_ru,
        )
        buttons.append(
            f'<p><a class="btn" href="{href}">{label}</a></p>',
        )

    steps_html = ""
    if steps:
        items = "".join(f"<li>{s}</li>" for s in steps)
        steps_html = f"<ul class=\"steps\">{items}</ul>"

    meta_lines: list[str] = []
    rid = corr_id.get("request_id")
    tid = corr_id.get("trace_id")
    svc = corr_id.get("service")
    if isinstance(rid, str) and rid.strip():
        meta_lines.append(html_module.escape(f"request_id: {rid.strip()}"))
    if isinstance(tid, str) and tid.strip():
        meta_lines.append(html_module.escape(f"trace_id: {tid.strip()}"))
    if isinstance(svc, str) and svc.strip():
        meta_lines.append(html_module.escape(f"service: {svc.strip()}"))

    footer = ""
    if meta_lines:
        inner = "".join(f"<div class=\"mono\">{line}</div>" for line in meta_lines)
        footer = f'<div class=\"meta\">{inner}</div>'

    css = """body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#16213e;color:#eaeaea;margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px}
.panel{max-width:560px;text-align:center}
h1{font-size:1.35rem;font-weight:600;margin:0 0 12px}
p.lead{font-size:1rem;line-height:1.5;margin:0 0 16px;color:rgba(234,234,234,.92)}
.steps{text-align:left;margin:16px auto 24px;padding-left:1.25rem;max-width:480px;line-height:1.45}
.steps li{margin:6px 0}
a.btn{display:inline-block;padding:10px 20px;background:#533483;color:#fff;text-decoration:none;border-radius:10px;font-weight:500}
a.btn:focus,a.btn:hover{background:#7b53a8}
.meta{margin-top:28px;text-align:center;font-size:12px;color:rgba(234,234,234,.55)}
.mono{font-family:ui-monospace,monospace;margin:4px 0}"""

    return f"""<!DOCTYPE html>
<html lang="{locale}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{css}</style>
</head>
<body>
<div class="panel">
<h1>{title}</h1>
<p class="lead">{message}</p>
{steps_html}
{''.join(buttons)}
{footer}
</div>
</body>
</html>"""


def oauth_error_correlation_ids(request: Request) -> dict[str, str]:
    out: dict[str, str] = {}
    rq = getattr(request.state, "request_id", None)
    tr = getattr(request.state, "trace_id", None)
    if isinstance(rq, str) and rq.strip():
        out["request_id"] = rq.strip()
    if isinstance(tr, str) and tr.strip():
        out["trace_id"] = tr.strip()
    path = request.url.path.strip("/")
    if path:
        first = path.split("/", 1)[0]
        if isinstance(first, str) and first.strip():
            out["service"] = first.strip()
    return out


def build_integration_oauth_simple_error_html(
    message: str,
    *,
    locale: OAuthErrorLocale,
    correlation: dict[str, str] | None = None,
) -> str:
    """Минимальная страница для ValueError в complete_oauth без структуры guided."""
    if not isinstance(message, str) or not message:
        raise ValueError("build_integration_oauth_simple_error_html: message обязателен")
    title_html = html_module.escape(
        "Connection failed" if locale == "en" else "Ошибка подключения",
    )
    message_html = html_module.escape(message)
    corr_id = correlation or {}

    meta_lines: list[str] = []
    rid = corr_id.get("request_id")
    tid = corr_id.get("trace_id")
    svc = corr_id.get("service")
    if isinstance(rid, str) and rid.strip():
        meta_lines.append(html_module.escape(f"request_id: {rid.strip()}"))
    if isinstance(tid, str) and tid.strip():
        meta_lines.append(html_module.escape(f"trace_id: {tid.strip()}"))
    if isinstance(svc, str) and svc.strip():
        meta_lines.append(html_module.escape(f"service: {svc.strip()}"))

    footer = ""
    if meta_lines:
        inner = "".join(f"<div class=\"mono\">{line}</div>" for line in meta_lines)
        footer = f"<div class=\"meta\">{inner}</div>"

    css = """body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#16213e;color:#eaeaea;margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px}
.panel{max-width:560px;text-align:center}
h1{font-size:1.35rem;font-weight:600;margin:0 0 12px}
p.lead{font-size:1rem;line-height:1.5;margin:0 0 16px;color:rgba(234,234,234,.92)}
.meta{margin-top:28px;text-align:center;font-size:12px;color:rgba(234,234,234,.55)}
.mono{font-family:ui-monospace,monospace;margin:4px 0}"""

    return f"""<!DOCTYPE html>
<html lang="{locale}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title_html}</title>
<style>{css}</style>
</head>
<body>
<div class="panel">
<h1>{title_html}</h1>
<p class="lead">{message_html}</p>
{footer}
</div>
</body>
</html>"""
