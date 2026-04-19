"""Регистрация connect/disconnect-hook'ов Sync в `core.websocket.notification_manager`.

Sync поддерживает свой Redis-presence (`sync:ws:presence:<user_id>`) поверх
платформенного `/sync/api/ws/notifications`. Это нужно чтобы:

  - Push-уведомления о новых сообщениях `deliver_channel_message_notification`
    пропускались, если пользователь уже подключён к Sync UI (см. `sync.mdc`,
    раздел про deliver_channel_message_notification).
  - GET `/company/members` возвращал поле `is_online`/`last_seen_at` без
    лишних round-trip'ов.

Hook'и регистрируются один раз на старте процесса sync через
`register_presence_hooks()` (вызывается из `apps/sync/main.py:on_startup`).
"""

from __future__ import annotations

from apps.sync.realtime.events import event_user_presence
from apps.sync.realtime.publish_events import publish_realtime_events
from apps.sync.ws_presence import (
    clear_sync_ws_presence,
    refresh_sync_ws_presence,
    set_last_seen_now,
)
from core.config import get_settings
from core.logging import get_logger
from core.websocket import notification_manager

logger = get_logger(__name__)

_HOOKS_REGISTERED = False


async def _on_connect(user_id: str, company_id: str | None, was_first: bool) -> None:
    settings = get_settings()
    redis_url = settings.database.redis_url
    if not redis_url:
        raise ValueError("database.redis_url не задан для sync presence hook.")
    await refresh_sync_ws_presence(redis_url, user_id)
    if was_first and company_id:
        await publish_realtime_events([
            event_user_presence(
                company_id=company_id,
                user_id=user_id,
                online=True,
                last_seen_at=None,
            ),
        ])


async def _on_disconnect(user_id: str, company_id: str | None, was_last: bool) -> None:
    if not was_last:
        return
    settings = get_settings()
    redis_url = settings.database.redis_url
    if not redis_url:
        raise ValueError("database.redis_url не задан для sync presence hook.")
    await clear_sync_ws_presence(redis_url, user_id)
    last_seen_iso = await set_last_seen_now(redis_url, user_id)
    if company_id:
        await publish_realtime_events([
            event_user_presence(
                company_id=company_id,
                user_id=user_id,
                online=False,
                last_seen_at=last_seen_iso,
            ),
        ])


def register_presence_hooks() -> None:
    """Идемпотентная регистрация. Повторный вызов — no-op."""
    global _HOOKS_REGISTERED
    if _HOOKS_REGISTERED:
        return
    notification_manager.register_connect_hook(_on_connect)
    notification_manager.register_disconnect_hook(_on_disconnect)
    _HOOKS_REGISTERED = True
    logger.info("Sync presence hooks зарегистрированы в core.websocket.notification_manager")
