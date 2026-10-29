"""Нормализация CDP URL для Playwright ``connect_over_cdp``.

``BrowserType.connect_over_cdp`` ожидает WebSocket debugger URL вида
``ws://host:port/devtools/browser/<id>``. Строка ``http://host:port`` или голый
``ws://host:port`` приводит к запросу ``ws://host:port/`` и ответу 404 от CDP.
"""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse

import httpx2

from core.types import parse_json_object


async def fetch_browser_web_socket_debugger_url(
    http_base: str,
    *,
    http_timeout_s: float = 5.0,
) -> str:
    """GET ``{http_base}/json/version`` и поле ``webSocketDebuggerUrl``."""
    base = http_base.strip().rstrip("/")
    if base == "":
        raise ValueError("http_base for CDP discovery must not be empty")
    version_url = f"{base}/json/version"
    async with httpx2.AsyncClient(timeout=http_timeout_s) as client:
        response = await client.get(version_url)
        _ = response.raise_for_status()
        try:
            data = parse_json_object(response.text, "CDP json/version response")
        except ValueError as exc:
            raise RuntimeError(
                f"CDP json/version at {version_url!r} is not JSON: {response.text[:500]!r}"
            ) from exc
    ws = data.get("webSocketDebuggerUrl")
    if not isinstance(ws, str) or ws.strip() == "":
        raise RuntimeError(
            f"json/version response at {version_url!r} without webSocketDebuggerUrl: {data!r}"
        )
    return ws.strip()


async def normalize_playwright_cdp_connect_url(
    url: str,
    *,
    http_timeout_s: float = 5.0,
) -> str:
    """Привести конфигурационный CDP URL к строке, пригодной для ``connect_over_cdp``."""
    raw = url.strip()
    if raw == "":
        raise ValueError("cdp_url must not be empty")
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    if scheme in ("http", "https"):
        if parsed.netloc == "":
            raise ValueError(f"CDP URL has no netloc: {raw!r}")
        http_base = urlunparse((scheme, parsed.netloc, "", "", "", "")).rstrip("/")
        return await fetch_browser_web_socket_debugger_url(
            http_base,
            http_timeout_s=http_timeout_s,
        )
    if scheme in ("ws", "wss"):
        path = parsed.path or ""
        if "/devtools/browser/" in path:
            return raw
        if parsed.netloc == "":
            raise ValueError(f"CDP URL has no netloc: {raw!r}")
        http_scheme = "https" if scheme == "wss" else "http"
        http_base = urlunparse((http_scheme, parsed.netloc, "", "", "", "")).rstrip("/")
        return await fetch_browser_web_socket_debugger_url(
            http_base,
            http_timeout_s=http_timeout_s,
        )
    raise ValueError(
        f"CDP URL for Playwright: expected http(s):// or ws(s)://; got {raw!r}"
    )
