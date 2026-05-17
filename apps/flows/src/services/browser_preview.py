"""Browser preview UI events and signed viewer URLs for flows chat."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urlencode

from apps.flows.config import FLOWS_PUBLIC_API_PREFIX, get_settings
from apps.flows.src.models.mcp import MCPCallResult, MCPServerConfig
from apps.flows.src.runtime.tool_call_context import get_active_tool_call_context
from core.logging import get_logger

logger = get_logger(__name__)

BROWSER_PREVIEW_EVENT_PREFIX = "browser.preview."
_BROWSER_SERVER_ID = "browser"
_TOKEN_TTL_SECONDS = 6 * 60 * 60


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padded = value + ("=" * (-len(value) % 4))
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _preview_secret() -> bytes:
    auth = get_settings().auth
    secret = auth.jwt_secret_key or "dev-secret-key-change-in-production"
    return str(secret).encode("utf-8")


def create_browser_preview_token(
    *,
    session_id: str,
    task_id: str,
    ttl_seconds: int = _TOKEN_TTL_SECONDS,
) -> str:
    payload = {
        "sid": session_id,
        "tid": task_id,
        "exp": int(time.time()) + int(ttl_seconds),
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    body = _b64url_encode(raw)
    sig = hmac.new(_preview_secret(), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64url_encode(sig)}"


def verify_browser_preview_token(*, token: str, session_id: str) -> dict[str, Any]:
    try:
        body, sig = token.split(".", 1)
    except ValueError as exc:
        raise ValueError("invalid preview token") from exc
    expected = _b64url_encode(
        hmac.new(_preview_secret(), body.encode("ascii"), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(expected, sig):
        raise ValueError("invalid preview token signature")
    try:
        payload = json.loads(_b64url_decode(body).decode("utf-8"))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("invalid preview token payload") from exc
    if not isinstance(payload, dict):
        raise ValueError("invalid preview token payload")
    if str(payload.get("sid", "")) != session_id:
        raise ValueError("preview token session mismatch")
    exp = int(payload.get("exp", 0) or 0)
    if exp <= int(time.time()):
        raise ValueError("preview token expired")
    return payload


def build_browser_preview_urls(*, session_id: str, task_id: str) -> dict[str, str]:
    token = create_browser_preview_token(session_id=session_id, task_id=task_id)
    encoded_session = quote(session_id, safe="")
    query = urlencode({"token": token})
    base = f"{FLOWS_PUBLIC_API_PREFIX}/browser-preview/sessions/{encoded_session}"
    return {
        "viewer_url": f"{base}/viewer?{query}",
        "screenshot_url": f"{base}/screenshot?{query}",
        "status_url": f"{base}/status?{query}",
    }


def is_browser_mcp_server(config: MCPServerConfig) -> bool:
    server_id = str(config.server_id or "").strip()
    url = str(config.url or "").strip()
    return server_id == _BROWSER_SERVER_ID or "/browser/api/" in url


def _mcp_result_json(result: MCPCallResult | None) -> dict[str, Any]:
    if result is None:
        return {}
    text = result.get_text().strip()
    if text == "":
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _session_id_from(tool_name: str, args: dict[str, Any], result: MCPCallResult | None) -> str:
    if tool_name == "browser_create_session":
        created = _mcp_result_json(result)
        sid = created.get("session_id")
        return str(sid).strip() if isinstance(sid, str) else ""
    sid = args.get("session_id")
    return str(sid).strip() if isinstance(sid, str) else ""


def _event_type_for_phase(tool_name: str, phase: str) -> str:
    if phase == "started":
        return f"{BROWSER_PREVIEW_EVENT_PREFIX}tool_started"
    if phase == "failed":
        return f"{BROWSER_PREVIEW_EVENT_PREFIX}tool_failed"
    if tool_name == "browser_create_session":
        return f"{BROWSER_PREVIEW_EVENT_PREFIX}session_started"
    if tool_name == "browser_close_session":
        return f"{BROWSER_PREVIEW_EVENT_PREFIX}session_closed"
    return f"{BROWSER_PREVIEW_EVENT_PREFIX}step_finished"


def _safe_args_preview(args: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "session_id",
        "url",
        "wait_policy",
        "selector",
        "load_state",
        "key",
        "ref",
        "page_mode",
    }
    return {key: args[key] for key in allowed if key in args}


async def emit_browser_preview_mcp_event(
    *,
    config: MCPServerConfig,
    tool_name: str,
    arguments: dict[str, Any],
    phase: str,
    result: MCPCallResult | None = None,
    error: str | None = None,
) -> None:
    """Emit best-effort browser preview event without changing MCP behavior."""
    try:
        await _emit_browser_preview_mcp_event(
            config=config,
            tool_name=tool_name,
            arguments=arguments,
            phase=phase,
            result=result,
            error=error,
        )
    except Exception as exc:  # pragma: no cover - preview must not break tools
        logger.warning(
            "browser_preview.event_emit_failed",
            event_type=f"{BROWSER_PREVIEW_EVENT_PREFIX}{phase}",
            tool_name=tool_name,
            error=str(exc),
        )


async def _emit_browser_preview_mcp_event(
    *,
    config: MCPServerConfig,
    tool_name: str,
    arguments: dict[str, Any],
    phase: str,
    result: MCPCallResult | None = None,
    error: str | None = None,
) -> None:
    if not is_browser_mcp_server(config):
        return
    if not tool_name.startswith("browser_"):
        return
    ctx = get_active_tool_call_context()
    if ctx is None or ctx.emitter is None:
        return

    event_type = _event_type_for_phase(tool_name, phase)
    state = ctx.state
    task_id = str(getattr(state, "task_id", "") or "")
    context_id = str(getattr(state, "context_id", "") or "")
    session_id = _session_id_from(tool_name, arguments, result)
    result_json = _mcp_result_json(result)

    payload: dict[str, Any] = {
        "server_id": config.server_id,
        "browser_tool_name": tool_name,
        "top_level_tool_name": ctx.tool_name,
        "tool_call_id": ctx.tool_call_id,
        "parent_tool_call_id": ctx.tool_call_id,
        "task_id": task_id,
        "context_id": context_id,
        "phase": phase,
        "status": "failed" if phase == "failed" else "running" if phase == "started" else "finished",
        "args": _safe_args_preview(arguments),
    }
    if session_id:
        payload["session_id"] = session_id
        payload["browser_session_id"] = session_id
        payload.update(build_browser_preview_urls(session_id=session_id, task_id=task_id))
    if "url" in arguments and isinstance(arguments["url"], str):
        payload["url"] = arguments["url"]
    if "final_url" in result_json and isinstance(result_json["final_url"], str):
        payload["final_url"] = result_json["final_url"]
    if "status_code" in result_json:
        payload["status_code"] = result_json["status_code"]
    if error:
        payload["error"] = error

    await ctx.emitter.emit_ui_event(
        event_type=event_type,
        payload=payload,
        version="1.0.0",
        timestamp=_now_iso(),
        source="browser",
        correlation_id=ctx.tool_call_id,
    )
