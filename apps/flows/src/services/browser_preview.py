"""UI-события browser preview и подписанные viewer URL для flows chat."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from urllib.parse import quote, urlencode

from pydantic import Field

from apps.flows.config import FLOWS_PUBLIC_API_PREFIX, get_settings
from apps.flows.src.models.mcp import MCPCallResult, MCPServerConfig
from apps.flows.src.runtime.tool_call_context import get_active_tool_call_context
from apps.flows.src.runtime_helpers.flow_ui_cards import card_block_id, show_browser_preview
from core.clients.redis_client import RedisClient
from core.logging import get_logger
from core.models.base import StrictBaseModel
from core.types import JsonObject, parse_json_object

logger = get_logger(__name__)

BROWSER_PREVIEW_EVENT_PREFIX = "browser.preview."
_BROWSER_SERVER_ID = "browser"
_TOKEN_TTL_SECONDS = 6 * 60 * 60
_ACTIVE_SESSION_KEY_PREFIX = "browser_preview:task:"

_redis: RedisClient | None = None


def _redis_client() -> RedisClient:
    global _redis
    if _redis is None:
        _redis = RedisClient(get_settings().database.redis_url)
    return _redis


def browser_preview_active_session_key(task_id: str) -> str:
    if not task_id.strip():
        raise ValueError("task_id обязателен")
    return f"{_ACTIVE_SESSION_KEY_PREFIX}{task_id.strip()}:active_session"


async def get_active_browser_session_for_task(task_id: str) -> str | None:
    """Активная browser-сессия задачи из Redis; None — сейчас нет открытой сессии."""
    raw = await _redis_client().get(browser_preview_active_session_key(task_id))
    if raw is None or raw.strip() == "":
        return None
    return raw.strip()


async def _store_active_browser_session(task_id: str, session_id: str) -> None:
    ok = await _redis_client().set(
        browser_preview_active_session_key(task_id),
        session_id,
        ttl=_TOKEN_TTL_SECONDS,
    )
    if not ok:
        logger.warning(
            "browser_preview.active_session_store_failed",
            task_id=task_id,
            browser_session_id=session_id,
        )


async def _clear_active_browser_session(task_id: str, session_id: str) -> None:
    key = browser_preview_active_session_key(task_id)
    current = await _redis_client().get(key)
    if current is None or current.strip() != session_id:
        return
    _ = await _redis_client().delete(key)


class BrowserPreviewTokenClaims(StrictBaseModel):
    sid: str
    tid: str
    exp: int = Field(ge=1)


class BrowserPreviewActiveSessionResponse(StrictBaseModel):
    session_id: str | None
    viewer_url: str | None = None
    screenshot_url: str | None = None
    status_url: str | None = None


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
    claims = BrowserPreviewTokenClaims(
        sid=session_id,
        tid=task_id,
        exp=int(time.time()) + int(ttl_seconds),
    )
    raw = claims.model_dump_json().encode("utf-8")
    body = _b64url_encode(raw)
    sig = hmac.new(_preview_secret(), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64url_encode(sig)}"


def verify_browser_preview_token(*, token: str, session_id: str) -> BrowserPreviewTokenClaims:
    claims = _verify_browser_preview_token_claims(token=token)
    if claims.sid != session_id:
        raise ValueError("preview token session mismatch")
    return claims


def verify_browser_preview_token_for_task(*, token: str, task_id: str) -> BrowserPreviewTokenClaims:
    claims = _verify_browser_preview_token_claims(token=token)
    if claims.tid != task_id:
        raise ValueError("preview token task mismatch")
    return claims


def _verify_browser_preview_token_claims(*, token: str) -> BrowserPreviewTokenClaims:
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
        claims = BrowserPreviewTokenClaims.model_validate_json(_b64url_decode(body))
    except ValueError as exc:
        raise ValueError("invalid preview token payload") from exc
    if claims.exp <= int(time.time()):
        raise ValueError("preview token expired")
    return claims


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


def _mcp_result_json(result: MCPCallResult | None) -> JsonObject:
    if result is None:
        return {}
    text = result.get_text().strip()
    if text == "":
        return {}
    try:
        return parse_json_object(text, "browser MCP result")
    except ValueError:
        return {}


def _session_id_from(tool_name: str, args: JsonObject, result: MCPCallResult | None) -> str:
    if tool_name == "browser_create_session":
        created = _mcp_result_json(result)
        sid = created.get("session_id")
        return str(sid).strip() if isinstance(sid, str) else ""
    sid = args.get("session_id")
    return str(sid).strip() if isinstance(sid, str) else ""


async def emit_browser_preview_mcp_event(
    *,
    config: MCPServerConfig,
    tool_name: str,
    arguments: JsonObject,
    phase: str,
    result: MCPCallResult | None = None,
    error: str | None = None,
) -> None:
    """Отправляет browser preview event best-effort, не меняя поведение MCP."""
    try:
        await _emit_browser_preview_mcp_event(
            config=config,
            tool_name=tool_name,
            arguments=arguments,
            phase=phase,
            result=result,
            error=error,
        )
    except Exception as exc:  # pragma: no cover — preview не должен ломать tools
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
    arguments: JsonObject,
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

    state = ctx.state
    task_id = state.task_id
    session_id = _session_id_from(tool_name, arguments, result)
    result_json = _mcp_result_json(result)

    if session_id:
        preview_urls = build_browser_preview_urls(session_id=session_id, task_id=task_id)
        page_url = arguments.get("url")
        final_url = result_json.get("final_url")
        current_url = final_url if isinstance(final_url, str) else page_url if isinstance(page_url, str) else ""
        title = f"{tool_name}: {error}" if error else current_url or tool_name
        _ = show_browser_preview(
            state,
            card_id=card_block_id("browser", ctx.tool_call_id),
            url=preview_urls["viewer_url"],
            title=title,
            screenshot_url=preview_urls["screenshot_url"],
            status="failed" if phase == "failed" else "running" if phase == "started" else "finished",
        )
        # Карточка нужна сразу, пока браузер работает, а не по завершении ноды.
        await ctx.emitter.emit_ui_events(state.drain_ui_events())

    # Viewer следит за задачей, а не за одной сессией: поддерживаем в Redis
    # маппинг task_id -> активная browser-сессия, чтобы после закрытия сессии
    # iframe мог переключиться на следующую.
    if session_id:
        if tool_name == "browser_close_session" and phase == "finished":
            await _clear_active_browser_session(task_id, session_id)
        elif phase in {"started", "finished"}:
            await _store_active_browser_session(task_id, session_id)
