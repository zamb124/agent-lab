"""Interactive browser preview gateway for chat tool chips."""

from __future__ import annotations

import html
import json
from typing import Annotated, Literal
from urllib.parse import quote

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, Response

from apps.browser.contracts.control_types import (
    ControlPointerClickBody,
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


async def _browser_get(
    session_id: str,
    suffix: str,
    *,
    params: dict[str, str] | None = None,
    timeout: float = 8.0,
) -> httpx.Response:
    async with get_httpx_client(timeout=timeout, strategy=ProxyStrategy.DIRECT_ONLY) as client:
        response = await client.get(
            _browser_control_url(session_id, suffix),
            params=params,
        )
        _ = await response.aread()
        return response


async def _browser_post(
    session_id: str,
    suffix: str,
    *,
    json_body: JsonObject,
    timeout: float = 8.0,
) -> httpx.Response:
    async with get_httpx_client(timeout=timeout, strategy=ProxyStrategy.DIRECT_ONLY) as client:
        response = await client.post(
            _browser_control_url(session_id, suffix),
            json=json_body,
        )
        _ = await response.aread()
        return response


def _raise_upstream_error(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    detail = response.text[:500] if response.text else response.reason_phrase
    raise HTTPException(status_code=response.status_code, detail=detail)


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


@router.get("/sessions/{session_id}/viewer", response_class=HTMLResponse)
async def browser_preview_viewer(
    session_id: str,
    token: Annotated[str, Query()],
) -> HTMLResponse:
    _ = _verify_token_or_403(token=token, session_id=session_id)
    api_prefix_json = json.dumps(FLOWS_PUBLIC_API_PREFIX)
    token_json = json.dumps(token)
    sid_json = json.dumps(session_id)
    sid_label = html.escape(session_id)
    return HTMLResponse(
        content=f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Browser preview</title>
  <style>
    :root {{
      color-scheme: dark;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #111318;
      color: #f3f5f7;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; min-height: 100vh; display: flex; flex-direction: column; }}
    header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 12px 16px;
      border-bottom: 1px solid rgba(255,255,255,0.12);
      background: #191d24;
    }}
    .title {{ min-width: 0; }}
    .title strong {{ display: block; font-size: 14px; font-weight: 650; }}
    .title span {{ display: block; margin-top: 3px; font-size: 12px; color: #aeb6c2; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .status {{ flex: 0 0 auto; font-size: 12px; color: #aeb6c2; }}
    main {{ flex: 1; display: grid; place-items: center; padding: 12px; overflow: auto; }}
    .frame {{
      position: relative;
      width: min(100%, 1440px);
      aspect-ratio: 16 / 9;
      min-height: 280px;
      display: grid;
      place-items: center;
      background: #0b0d11;
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: 8px;
      overflow: hidden;
    }}
    img {{
      display: block;
      width: 100%;
      height: 100%;
      object-fit: contain;
      background: #0b0d11;
      cursor: crosshair;
      user-select: none;
      -webkit-user-drag: none;
    }}
    img.clicking {{
      cursor: progress;
    }}
    .empty {{ padding: 24px; color: #aeb6c2; font-size: 14px; }}
  </style>
</head>
<body>
  <header>
    <div class="title">
      <strong>Browser preview</strong>
      <span id="url">Session {sid_label}</span>
    </div>
    <div class="status" id="status">connecting</div>
  </header>
  <main>
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
    let stopped = false;
    let pendingClick = false;
    let refreshTimer = null;

    function setStatus(text) {{
      status.textContent = text;
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
          setStatus(`live - click to interact ${{new Date().toLocaleTimeString()}}`);
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
      setStatus('clicking');
      try {{
        const res = await fetch(`${{base}}/click?token=${{encodeURIComponent(token)}}`, {{
          method: 'POST',
          credentials: 'same-origin',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{
            ...point,
            button: 'left',
            click_count: 1,
          }}),
        }});
        if (!res.ok) throw new Error(String(res.status));
        setStatus('clicked');
        scheduleFrame(120);
        refreshStatus();
      }} catch (_) {{
        setStatus('click failed');
      }} finally {{
        window.setTimeout(() => {{
          pendingClick = false;
          screen.classList.remove('clicking');
        }}, 180);
      }}
    }}

    screen.addEventListener('click', sendClick);
    refreshStatus();
    refreshFrame();
    setInterval(refreshStatus, 1600);
  </script>
</body>
</html>""",
        headers={"Cache-Control": "no-store, max-age=0"},
    )
