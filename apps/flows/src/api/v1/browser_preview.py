"""Интерактивный browser preview gateway для tool chips в чате."""

from __future__ import annotations

import html
import json
from typing import Annotated, Literal
from urllib.parse import quote

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, Response

from apps.browser.contracts.control_types import (
    ControlHumanTakeoverBody,
    ControlPointerClickBody,
    ControlPointerKeyBody,
    ControlPointerTextBody,
    ControlSessionStatusResponse,
)
from apps.flows.config import FLOWS_PUBLIC_API_PREFIX, get_settings
from apps.flows.src.services.browser_preview import (
    BrowserPreviewTokenClaims,
    verify_browser_preview_token,
)
from core.http import ProxyStrategy, get_httpx_client
from core.types import JsonObject, parse_json_object, require_json_object

router = APIRouter(tags=["browser-preview"])


def _verify_token_or_403(*, token: str, session_id: str) -> BrowserPreviewTokenClaims:
    try:
        return verify_browser_preview_token(token=token, session_id=session_id)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _browser_control_url(session_id: str, suffix: str) -> str:
    base = get_settings().server.get_service_url("browser").rstrip("/")
    encoded_session = quote(session_id, safe="")
    return f"{base}/browser/api/v1/control/sessions/{encoded_session}/{suffix.lstrip('/')}"


def _http_error_detail(exc: httpx.HTTPError) -> str:
    message = str(exc).strip()
    exc_name = exc.__class__.__name__
    if message:
        return f"browser service unavailable: {exc_name}: {message}"
    return f"browser service unavailable: {exc_name}"


async def _browser_get(
    session_id: str,
    suffix: str,
    *,
    params: dict[str, str] | None = None,
    timeout: float = 8.0,
) -> httpx.Response:
    try:
        async with get_httpx_client(timeout=timeout, strategy=ProxyStrategy.DIRECT_ONLY) as client:
            response = await client.get(
                _browser_control_url(session_id, suffix),
                params=params,
            )
            _ = await response.aread()
            return response
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=_http_error_detail(exc)) from exc


async def _browser_post(
    session_id: str,
    suffix: str,
    *,
    json_body: JsonObject,
    timeout: float = 8.0,
) -> httpx.Response:
    try:
        async with get_httpx_client(timeout=timeout, strategy=ProxyStrategy.DIRECT_ONLY) as client:
            response = await client.post(
                _browser_control_url(session_id, suffix),
                json=json_body,
            )
            _ = await response.aread()
            return response
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=_http_error_detail(exc)) from exc


def _response_detail(response: httpx.Response) -> str:
    text = response.text
    if text:
        try:
            payload = parse_json_object(text, "browser upstream error")
        except ValueError:
            return text[:500]
        detail = payload.get("detail")
        if isinstance(detail, str) and detail:
            try:
                nested = parse_json_object(detail, "browser upstream nested error")
            except ValueError:
                return detail[:500]
            nested_detail = nested.get("detail")
            if isinstance(nested_detail, str) and nested_detail:
                return nested_detail[:500]
            return detail[:500]
    return response.reason_phrase or "browser upstream error"


def _raise_upstream_error(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    raise HTTPException(status_code=response.status_code, detail=_response_detail(response))


@router.get("/sessions/{session_id}/status")
async def browser_preview_status(
    session_id: str,
    token: Annotated[str, Query()],
) -> JSONResponse:
    _ = _verify_token_or_403(token=token, session_id=session_id)
    response = await _browser_get(session_id, "status", timeout=5.0)
    _raise_upstream_error(response)
    try:
        status = ControlSessionStatusResponse.model_validate_json(response.text)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="browser status returned invalid json") from exc
    return JSONResponse(
        content=require_json_object(status.model_dump(mode="json"), "browser status response"),
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@router.get("/sessions/{session_id}/screenshot")
async def browser_preview_screenshot(
    session_id: str,
    token: Annotated[str, Query()],
    image_format: Annotated[Literal["jpeg", "png"], Query(alias="format")] = "jpeg",
    quality: Annotated[int, Query(ge=1, le=100)] = 70,
    full_page: Annotated[bool, Query()] = False,
) -> Response:
    _ = _verify_token_or_403(token=token, session_id=session_id)
    response = await _browser_get(
        session_id,
        "screenshot",
        params={
            "format": image_format,
            "quality": str(quality),
            "full_page": str(full_page).lower(),
        },
        timeout=10.0,
    )
    _raise_upstream_error(response)
    response_headers = dict(response.headers.items())
    media_type = response_headers.get("content-type") or f"image/{image_format}"
    return Response(
        content=response.content,
        media_type=media_type,
        headers={
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
        },
    )


@router.post("/sessions/{session_id}/click")
async def browser_preview_click(
    session_id: str,
    body: ControlPointerClickBody,
    token: Annotated[str, Query()],
) -> JSONResponse:
    _ = _verify_token_or_403(token=token, session_id=session_id)
    response = await _browser_post(
        session_id,
        "pointer/click",
        json_body=require_json_object(body.model_dump(mode="json"), "browser pointer click body"),
        timeout=10.0,
    )
    _raise_upstream_error(response)
    try:
        payload = parse_json_object(response.text, "browser pointer click response")
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="browser click returned invalid json") from exc
    return JSONResponse(
        content=payload,
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@router.post("/sessions/{session_id}/takeover")
async def browser_preview_takeover(
    session_id: str,
    body: ControlHumanTakeoverBody,
    token: Annotated[str, Query()],
) -> JSONResponse:
    _ = _verify_token_or_403(token=token, session_id=session_id)
    response = await _browser_post(
        session_id,
        "human-takeover",
        json_body=require_json_object(body.model_dump(mode="json"), "browser human takeover body"),
        timeout=5.0,
    )
    _raise_upstream_error(response)
    try:
        payload = parse_json_object(response.text, "browser human takeover response")
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="browser takeover returned invalid json") from exc
    return JSONResponse(
        content=payload,
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@router.post("/sessions/{session_id}/takeover/release")
async def browser_preview_takeover_release(
    session_id: str,
    token: Annotated[str, Query()],
) -> JSONResponse:
    _ = _verify_token_or_403(token=token, session_id=session_id)
    response = await _browser_post(
        session_id,
        "human-takeover/release",
        json_body={},
        timeout=5.0,
    )
    _raise_upstream_error(response)
    try:
        payload = parse_json_object(response.text, "browser human takeover release response")
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="browser takeover release returned invalid json") from exc
    return JSONResponse(
        content=payload,
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@router.post("/sessions/{session_id}/key")
async def browser_preview_key(
    session_id: str,
    body: ControlPointerKeyBody,
    token: Annotated[str, Query()],
) -> JSONResponse:
    _ = _verify_token_or_403(token=token, session_id=session_id)
    response = await _browser_post(
        session_id,
        "pointer/key",
        json_body=require_json_object(body.model_dump(mode="json"), "browser pointer key body"),
        timeout=5.0,
    )
    _raise_upstream_error(response)
    try:
        payload = parse_json_object(response.text, "browser pointer key response")
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="browser key returned invalid json") from exc
    return JSONResponse(
        content=payload,
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@router.post("/sessions/{session_id}/text")
async def browser_preview_text(
    session_id: str,
    body: ControlPointerTextBody,
    token: Annotated[str, Query()],
) -> JSONResponse:
    _ = _verify_token_or_403(token=token, session_id=session_id)
    response = await _browser_post(
        session_id,
        "pointer/text",
        json_body=require_json_object(body.model_dump(mode="json"), "browser pointer text body"),
        timeout=5.0,
    )
    _raise_upstream_error(response)
    try:
        payload = parse_json_object(response.text, "browser pointer text response")
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="browser text returned invalid json") from exc
    return JSONResponse(
        content=payload,
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@router.get("/sessions/{session_id}/viewer", response_class=HTMLResponse)
async def browser_preview_viewer(
    session_id: str,
    token: Annotated[str, Query()],
    theme: Annotated[Literal["dark", "light"], Query()] = "dark",
) -> HTMLResponse:
    _ = _verify_token_or_403(token=token, session_id=session_id)
    api_prefix_json = json.dumps(FLOWS_PUBLIC_API_PREFIX)
    token_json = json.dumps(token)
    sid_json = json.dumps(session_id)
    sid_label = html.escape(session_id)
    theme_attr = html.escape(theme)
    return HTMLResponse(
        content=f"""<!doctype html>
<html lang="en" data-theme="{theme_attr}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Browser preview</title>
  <style>
    :root {{
      color-scheme: dark;
      --bp-page-bg: #111318;
      --bp-main-bg: #111318;
      --bp-header-bg: #191d24;
      --bp-frame-bg: #0b0d11;
      --bp-text: #f3f5f7;
      --bp-muted: #aeb6c2;
      --bp-border: rgba(255,255,255,0.12);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bp-page-bg);
      color: var(--bp-text);
    }}
    :root[data-theme="light"] {{
      color-scheme: light;
      --bp-page-bg: #f7f8fb;
      --bp-main-bg: #f7f8fb;
      --bp-header-bg: rgba(255,255,255,0.94);
      --bp-frame-bg: #eef1f6;
      --bp-text: #111827;
      --bp-muted: #64748b;
      --bp-border: rgba(15,23,42,0.12);
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; min-height: 100vh; display: flex; flex-direction: column; background: var(--bp-page-bg); }}
    header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 12px 16px;
      border-bottom: 1px solid var(--bp-border);
      background: var(--bp-header-bg);
    }}
    .title {{ min-width: 0; }}
    .title strong {{ display: block; font-size: 14px; font-weight: 650; }}
    .title span {{ display: block; margin-top: 3px; font-size: 12px; color: var(--bp-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .controls {{ display: flex; align-items: center; gap: 10px; flex: 0 0 auto; }}
    .control-btn {{
      appearance: none;
      border: 1px solid var(--bp-border);
      border-radius: 7px;
      background: var(--bp-main-bg);
      color: var(--bp-text);
      font: inherit;
      font-size: 12px;
      font-weight: 650;
      line-height: 1;
      padding: 8px 10px;
      cursor: pointer;
    }}
    .control-btn[aria-pressed="true"] {{
      border-color: #7c8cff;
      background: rgba(124,140,255,0.14);
    }}
    .status {{ flex: 0 0 auto; font-size: 12px; color: var(--bp-muted); }}
    main {{ flex: 1; display: grid; place-items: center; padding: 12px; overflow: auto; background: var(--bp-main-bg); outline: none; }}
    .frame {{
      position: relative;
      width: min(100%, 1440px);
      aspect-ratio: 16 / 9;
      min-height: 280px;
      display: grid;
      place-items: center;
      background: var(--bp-frame-bg);
      border: 1px solid var(--bp-border);
      border-radius: 8px;
      overflow: hidden;
    }}
    img {{
      display: block;
      width: 100%;
      height: 100%;
      object-fit: contain;
      background: var(--bp-frame-bg);
      cursor: crosshair;
      user-select: none;
      -webkit-user-drag: none;
    }}
    img.clicking {{
      cursor: progress;
    }}
    .empty {{ padding: 24px; color: var(--bp-muted); font-size: 14px; }}
  </style>
</head>
<body>
  <header>
    <div class="title">
      <strong>Browser preview</strong>
      <span id="url">Session {sid_label}</span>
    </div>
    <div class="controls">
      <button class="control-btn" id="takeoverBtn" type="button" aria-pressed="false">Take control</button>
      <div class="status" id="status">connecting</div>
    </div>
  </header>
  <main id="viewport" tabindex="0">
    <div class="frame">
      <img id="screen" alt="Browser screenshot" style="display:none" />
      <div id="empty" class="empty">Waiting for browser frame</div>
    </div>
  </main>
  <script>
    const apiPrefix = {api_prefix_json};
    const sessionId = {sid_json};
    const token = {token_json};
    const base = `${{apiPrefix}}/browser-preview/sessions/${{encodeURIComponent(sessionId)}}`;
    const screen = document.getElementById('screen');
    const empty = document.getElementById('empty');
    const status = document.getElementById('status');
    const urlEl = document.getElementById('url');
    const viewport = document.getElementById('viewport');
    const takeoverBtn = document.getElementById('takeoverBtn');
    let stopped = false;
    let pendingClick = false;
    let takeoverActive = false;
    let refreshTimer = null;

    function setStatus(text) {{
      status.textContent = text;
    }}

    function setTakeover(active) {{
      takeoverActive = Boolean(active);
      takeoverBtn.setAttribute('aria-pressed', takeoverActive ? 'true' : 'false');
      takeoverBtn.textContent = takeoverActive ? 'Release control' : 'Take control';
    }}

    async function responseErrorText(res) {{
      let text = '';
      try {{
        const data = await res.json();
        if (data && typeof data.detail === 'string' && data.detail.length > 0) {{
          text = data.detail;
        }}
      }} catch (_) {{
        try {{
          text = await res.text();
        }} catch (_) {{
          text = '';
        }}
      }}
      return text || `HTTP ${{res.status}}`;
    }}

    async function postJson(path, body) {{
      const res = await fetch(`${{base}}/${{path}}?token=${{encodeURIComponent(token)}}`, {{
        method: 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(body || {{}}),
      }});
      if (!res.ok) throw new Error(await responseErrorText(res));
      try {{
        return await res.json();
      }} catch (_) {{
        return {{}};
      }}
    }}

    async function ensureTakeover() {{
      if (takeoverActive) return;
      setStatus('taking control');
      const data = await postJson('takeover', {{ owner: 'flows.browser_preview' }});
      setTakeover(data && data.human_takeover === true);
      if (!takeoverActive) setTakeover(true);
    }}

    async function releaseTakeover() {{
      if (!takeoverActive) return;
      setStatus('releasing control');
      await postJson('takeover/release', {{}});
      setTakeover(false);
      setStatus('control released');
      refreshStatus();
    }}

    function showPreviewError(text) {{
      screen.style.display = 'none';
      empty.style.display = 'block';
      empty.textContent = text;
      setStatus(text);
    }}

    function scheduleFrame(delayMs) {{
      if (stopped) return;
      if (refreshTimer !== null) {{
        window.clearTimeout(refreshTimer);
      }}
      refreshTimer = window.setTimeout(() => {{
        refreshTimer = null;
        refreshFrame();
      }}, delayMs);
    }}

    async function refreshStatus() {{
      try {{
        const res = await fetch(`${{base}}/status?token=${{encodeURIComponent(token)}}`, {{ credentials: 'same-origin', cache: 'no-store' }});
        if (!res.ok) throw new Error(String(res.status));
        const data = await res.json();
        if (data && typeof data.url === 'string' && data.url.length > 0) {{
          urlEl.textContent = data.url;
        }}
        setTakeover(data && data.human_takeover === true);
        if (data && data.closed === true) {{
          setStatus('closed');
          stopped = true;
        }}
      }} catch (_) {{
        if (!stopped) setStatus('status unavailable');
      }}
    }}

    function refreshFrame() {{
      if (stopped) return;
      const img = new Image();
      img.onload = () => {{
        screen.src = img.src;
        screen.style.display = 'block';
        empty.style.display = 'none';
        if (!pendingClick) {{
          setStatus(`${{takeoverActive ? 'human control' : 'live - click to interact'}} ${{new Date().toLocaleTimeString()}}`);
        }}
        scheduleFrame(900);
      }};
      img.onerror = () => {{
        screen.style.display = 'none';
        empty.style.display = 'block';
        if (!stopped) {{
          setStatus('waiting');
          scheduleFrame(1400);
        }}
      }};
      img.src = `${{base}}/screenshot?token=${{encodeURIComponent(token)}}&format=jpeg&quality=70&_=${{Date.now()}}`;
    }}

    function imagePointFromEvent(event) {{
      if (!screen.naturalWidth || !screen.naturalHeight) return null;
      const rect = screen.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) return null;
      const imageRatio = screen.naturalWidth / screen.naturalHeight;
      const boxRatio = rect.width / rect.height;
      let left = rect.left;
      let top = rect.top;
      let width = rect.width;
      let height = rect.height;
      if (boxRatio > imageRatio) {{
        width = height * imageRatio;
        left = rect.left + (rect.width - width) / 2;
      }} else {{
        height = width / imageRatio;
        top = rect.top + (rect.height - height) / 2;
      }}
      const relX = event.clientX - left;
      const relY = event.clientY - top;
      if (relX < 0 || relY < 0 || relX > width || relY > height) return null;
      return {{
        x: relX / width * screen.naturalWidth,
        y: relY / height * screen.naturalHeight,
        image_width: screen.naturalWidth,
        image_height: screen.naturalHeight,
      }};
    }}

    async function sendClick(event) {{
      event.preventDefault();
      const point = imagePointFromEvent(event);
      if (!point || stopped) return;
      pendingClick = true;
      screen.classList.add('clicking');
      try {{
        viewport.focus({{ preventScroll: true }});
        await ensureTakeover();
        setStatus('clicking');
        await postJson('click', {{
          ...point,
          button: 'left',
          click_count: 1,
        }});
        setStatus('clicked');
        scheduleFrame(120);
        refreshStatus();
      }} catch (err) {{
        const message = err && typeof err.message === 'string' && err.message.length > 0
          ? err.message
          : 'click failed';
        showPreviewError(message);
      }} finally {{
        window.setTimeout(() => {{
          pendingClick = false;
          screen.classList.remove('clicking');
        }}, 180);
      }}
    }}

    const keyNames = new Set([
      'Enter', 'Tab', 'Backspace', 'Delete', 'Escape',
      'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight',
      'Home', 'End', 'PageUp', 'PageDown',
    ]);

    async function sendText(text) {{
      if (stopped || !text) return;
      await ensureTakeover();
      setStatus('typing');
      await postJson('text', {{ text }});
      scheduleFrame(120);
    }}

    async function sendKey(key) {{
      if (stopped || !key) return;
      await ensureTakeover();
      setStatus(`key ${{key}}`);
      await postJson('key', {{ key }});
      scheduleFrame(120);
    }}

    async function handleKeydown(event) {{
      if (event.target === takeoverBtn) return;
      if (event.metaKey || event.ctrlKey) return;
      if (event.key.length === 1 && !event.altKey) {{
        event.preventDefault();
        try {{
          await sendText(event.key);
        }} catch (err) {{
          showPreviewError(err && err.message ? err.message : 'typing failed');
        }}
        return;
      }}
      if (keyNames.has(event.key)) {{
        event.preventDefault();
        try {{
          await sendKey(event.key);
        }} catch (err) {{
          showPreviewError(err && err.message ? err.message : 'key failed');
        }}
      }}
    }}

    async function handlePaste(event) {{
      const text = event.clipboardData ? event.clipboardData.getData('text') : '';
      if (!text) return;
      event.preventDefault();
      try {{
        await sendText(text);
      }} catch (err) {{
        showPreviewError(err && err.message ? err.message : 'paste failed');
      }}
    }}

    takeoverBtn.addEventListener('click', async () => {{
      try {{
        if (takeoverActive) {{
          await releaseTakeover();
        }} else {{
          await ensureTakeover();
          viewport.focus({{ preventScroll: true }});
          setStatus('human control');
        }}
      }} catch (err) {{
        showPreviewError(err && err.message ? err.message : 'control handoff failed');
      }}
    }});
    screen.addEventListener('click', sendClick);
    window.addEventListener('keydown', handleKeydown);
    window.addEventListener('paste', handlePaste);
    window.addEventListener('beforeunload', () => {{
      if (!takeoverActive) return;
      try {{
        fetch(`${{base}}/takeover/release?token=${{encodeURIComponent(token)}}`, {{
          method: 'POST',
          credentials: 'same-origin',
          keepalive: true,
          headers: {{ 'Content-Type': 'application/json' }},
          body: '{{}}',
        }});
      }} catch (_) {{}}
    }});
    refreshStatus();
    refreshFrame();
    setInterval(refreshStatus, 1600);
  </script>
</body>
</html>""",
        headers={"Cache-Control": "no-store, max-age=0"},
    )
