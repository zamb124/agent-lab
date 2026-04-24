"""
Проверка чернового конфига триггера (до сохранения): Telegram getMe, cron, и т.д.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from croniter import croniter
from croniter.croniter import CroniterBadCronError

from apps.flows.config import get_settings
from apps.flows.src.models import TriggerType
from core.http import get_httpx_client
from core.logging import get_logger

logger = get_logger(__name__)

VerifyResult = Tuple[bool, Dict[str, Any], Optional[str], Optional[str]]


async def verify_telegram_config(config: Dict[str, Any]) -> VerifyResult:
    token = config.get("bot_token")
    if not token or not str(token).strip():
        return False, {}, "bot_token_required", "Укажите токен бота (bot_token)."

    token_s = str(token).strip()
    if token_s.startswith("@var:"):
        return (
            False,
            {},
            "bot_token_unresolved",
            "Сервер не подставил значение @var: для токена. Проверьте имя переменной и вызов проверки.",
        )

    base = get_settings().telegram.api_base
    url = f"{base.rstrip('/')}/bot{token_s}/getMe"
    try:
        async with get_httpx_client() as client:
            response = await client.get(url, timeout=20.0)
    except Exception as e:
        logger.warning("Telegram getMe request failed: %s", e)
        return False, {}, "http_error", str(e)

    try:
        data = response.json()
    except Exception as e:
        return False, {}, "invalid_response", f"Некорректный JSON ответа: {e}"

    if not data.get("ok"):
        desc = data.get("description")
        if isinstance(desc, str) and desc:
            return False, {
                "http_status": response.status_code,
                "response": data,
            }, "telegram_error", desc
        return False, {
            "http_status": response.status_code,
            "response": data,
        }, "telegram_error", "Telegram API вернул ok=false"

    result = data.get("result")
    meta: Dict[str, Any] = {
        "api": "getMe",
        "http_status": response.status_code,
    }
    if isinstance(result, dict):
        for key in ("id", "is_bot", "first_name", "username", "can_join_groups", "supports_inline_queries"):
            if key in result:
                meta[key] = result[key]

    return True, meta, None, None


def verify_cron_config(config: Dict[str, Any]) -> VerifyResult:
    raw = config.get("cron")
    if raw is None or not str(raw).strip():
        return False, {}, "cron_required", "Укажите выражение cron."
    expr = str(raw).strip()
    tz_name = config.get("timezone")
    if tz_name is not None and not str(tz_name).strip():
        return False, {}, "timezone_empty", "timezone не может быть пустой строкой."
    now = datetime.now(timezone.utc)
    try:
        it = croniter(expr, now)
        next0 = it.get_next(datetime)
        next1 = it.get_next(datetime)
    except (CroniterBadCronError, ValueError, KeyError) as e:
        return False, {"expression": expr}, "cron_invalid", str(e)
    return True, {
        "expression": expr,
        "timezone": str(tz_name).strip() if tz_name is not None else "UTC",
        "next_runs_utc": [next0.isoformat(), next1.isoformat()],
    }, None, None


def verify_webhook_config(
    config: Dict[str, Any], flow_id: str, trigger_id: Optional[str]
) -> VerifyResult:
    secret = config.get("secret_token")
    meta: Dict[str, Any] = {
        "has_secret": bool(secret and str(secret).strip()),
        "flow_id": flow_id,
    }
    tid = str(trigger_id).strip() if trigger_id else ""
    if tid:
        meta["path_template"] = f"/flows/api/v1/triggers/webhook/{flow_id}/{tid}"
    return True, meta, None, None


def verify_email_config(config: Dict[str, Any]) -> VerifyResult:
    provider = str(config.get("provider", "imap")).strip() or "imap"
    meta = {
        "provider": provider,
        "imap_host": config.get("imap_host"),
        "imap_port": config.get("imap_port", 993),
    }
    return (
        True,
        meta,
        None,
        None,
    )


def verify_redis_config(config: Dict[str, Any]) -> VerifyResult:
    ch = config.get("channel")
    if ch is None or not str(ch).strip():
        return False, {}, "channel_required", "Укажите redis channel."
    return True, {
        "channel": str(ch).strip(),
        "pattern": bool(config.get("pattern", False)),
    }, None, None


async def verify_trigger_draft(
    trigger_type: TriggerType,
    config: Dict[str, Any],
    flow_id: str,
    trigger_id: Optional[str],
) -> VerifyResult:
    if trigger_type == TriggerType.TELEGRAM:
        return await verify_telegram_config(config)
    if trigger_type == TriggerType.CRON:
        return verify_cron_config(config)
    if trigger_type == TriggerType.WEBHOOK:
        return verify_webhook_config(config, flow_id, trigger_id)
    if trigger_type == TriggerType.EMAIL:
        return verify_email_config(config)
    if trigger_type == TriggerType.REDIS:
        return verify_redis_config(config)
    return (
        False,
        {},
        "unsupported",
        f"Проверка для типа {trigger_type} не настроена.",
    )
