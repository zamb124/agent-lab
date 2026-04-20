"""
Менеджер WebSocket каналов платформы.

Единственный публичный канал uplink → UI: `platform:ui_events`. В этот канал
бэкенд-сервисы публикуют `UIEvent` через `core/ui_events/dispatcher.py`. Менеджер
парсит конверт `{ "target": ..., "event": ... }`, проверяет адресацию (user/company/broadcast)
и форвардит сериализованный `event` в WS-сокеты адресатов.

Никакой бизнес-логики; никакой кастомной формы фрейма — фронту приходит
ровно сериализованный `UIEvent` (type/payload/meta), как в контракте
`core/ui_events/contract.py`.
"""

from __future__ import annotations

import asyncio
import json
from typing import Dict, Optional, Set, Tuple

import redis.asyncio as aioredis
from fastapi import WebSocket

from core.logging import get_logger
from core.ui_events.dispatcher import UI_EVENTS_REDIS_CHANNEL

logger = get_logger(__name__)


class NotificationManager:
    """Менеджер WebSocket-сокетов для всех сервисов платформы.

    Поддерживает регистрацию hooks (`register_connect_hook` /
    `register_disconnect_hook`) — сервис вызывает на `on_startup` и
    подписывается на события подключения/отключения, чтобы реализовать
    presence-tracking, online-статусы и т.п.
    """

    def __init__(self) -> None:
        self._connections: Dict[str, Set[WebSocket]] = {}
        self._socket_meta: Dict[WebSocket, Tuple[str, Optional[str]]] = {}
        self._connection_lock = asyncio.Lock()
        self._redis_task: Optional[asyncio.Task] = None
        self._redis_client: Optional[aioredis.Redis] = None
        self._connect_hooks: list = []
        self._disconnect_hooks: list = []

    def register_connect_hook(self, hook) -> None:
        """Hook вида `async def hook(user_id: str, company_id: str | None,
        was_first_connection: bool) -> None`."""
        if not callable(hook):
            raise TypeError("connect hook must be callable")
        self._connect_hooks.append(hook)

    def register_disconnect_hook(self, hook) -> None:
        """Hook вида `async def hook(user_id: str, company_id: str | None,
        was_last_connection: bool) -> None`."""
        if not callable(hook):
            raise TypeError("disconnect hook must be callable")
        self._disconnect_hooks.append(hook)

    async def connect(self, websocket: WebSocket, user_id: str, company_id: Optional[str] = None) -> None:
        async with self._connection_lock:
            existing = self._connections.get(user_id)
            was_first_connection = not existing
            self._connections.setdefault(user_id, set()).add(websocket)
            self._socket_meta[websocket] = (user_id, company_id)
            logger.info(
                "WS connected: user=%s company=%s total_for_user=%d",
                user_id,
                company_id,
                len(self._connections[user_id]),
            )
        for hook in self._connect_hooks:
            try:
                await hook(user_id, company_id, was_first_connection)
            except Exception:
                logger.exception("WS connect hook failed: user=%s", user_id)

    async def disconnect(self, websocket: WebSocket, user_id: str) -> None:
        was_last_connection = False
        company_id: Optional[str] = None
        async with self._connection_lock:
            meta = self._socket_meta.pop(websocket, None)
            if meta is not None:
                _, company_id = meta
            sockets = self._connections.get(user_id)
            if sockets is not None:
                sockets.discard(websocket)
                if not sockets:
                    self._connections.pop(user_id, None)
                    was_last_connection = True
            logger.info("WS disconnected: user=%s last=%s", user_id, was_last_connection)
        for hook in self._disconnect_hooks:
            try:
                await hook(user_id, company_id, was_last_connection)
            except Exception:
                logger.exception("WS disconnect hook failed: user=%s", user_id)

    def is_user_connected(self, user_id: str) -> bool:
        sockets = self._connections.get(user_id)
        return bool(sockets) and len(sockets) > 0

    async def publish_ui_envelope(self, envelope_json: str) -> None:
        """Публикация уже сериализованного UI-конверта (вызывается dispatcher'ом).

        В HTTP-процессах `_redis_client` инициализирован `start_redis_listener`
        на `on_startup`. В TaskIQ worker отдельного listener нет — клиент
        поднимается лениво из `DATABASE__REDIS_URL` (см. `core/config`),
        чтобы один и тот же dispatcher работал из любого процесса платформы.
        """
        client = await self._ensure_publisher_client()
        if client is None:
            logger.warning("Redis client not available; UI event dropped")
            return
        await client.publish(UI_EVENTS_REDIS_CHANNEL, envelope_json)

    async def _ensure_publisher_client(self) -> Optional[aioredis.Redis]:
        if self._redis_client is not None:
            return self._redis_client
        from core.config import get_settings

        settings = get_settings()
        redis_url = getattr(settings.database, "redis_url", None)
        if not redis_url:
            return None
        self._redis_client = aioredis.from_url(redis_url)
        logger.info("Redis publisher client lazy-initialized for UI events")
        return self._redis_client

    async def _send_event_to_sockets(self, sockets: Set[WebSocket], event_text: str, label: str) -> None:
        dead: Set[WebSocket] = set()
        for ws in list(sockets):
            try:
                await ws.send_text(event_text)
            except Exception as exc:
                logger.warning("WS send failed (%s): %s", label, exc)
                dead.add(ws)
        if dead:
            async with self._connection_lock:
                for ws in dead:
                    meta = self._socket_meta.pop(ws, None)
                    if meta:
                        uid, _ = meta
                        bucket = self._connections.get(uid)
                        if bucket is not None:
                            bucket.discard(ws)
                            if not bucket:
                                self._connections.pop(uid, None)

    async def _deliver_envelope(self, envelope: dict) -> None:
        target = envelope.get("target") or {}
        event = envelope.get("event")
        if not isinstance(event, dict) or "type" not in event:
            logger.warning("UIEvent envelope without event/type, dropped")
            return

        event_text = json.dumps(event, ensure_ascii=False)
        user_id = target.get("user_id")
        company_id = target.get("company_id")
        broadcast = bool(target.get("broadcast"))

        if user_id:
            sockets = self._connections.get(user_id)
            if not sockets:
                return
            await self._send_event_to_sockets(sockets, event_text, f"user={user_id}")
            return

        if company_id:
            matched: Set[WebSocket] = set()
            for ws, (uid, cid) in self._socket_meta.items():
                if cid == company_id:
                    matched.add(ws)
            await self._send_event_to_sockets(matched, event_text, f"company={company_id}")
            return

        if broadcast:
            all_sockets: Set[WebSocket] = set(self._socket_meta.keys())
            await self._send_event_to_sockets(all_sockets, event_text, "broadcast")
            return

        logger.warning("UIEvent envelope without valid target, dropped")

    async def start_redis_listener(self, redis_url: str) -> None:
        if self._redis_task is not None:
            logger.warning("Redis UI events listener already running")
            return
        self._redis_client = aioredis.from_url(redis_url)
        self._redis_task = asyncio.create_task(self._redis_loop())
        logger.info("Redis UI events listener started on channel %s", UI_EVENTS_REDIS_CHANNEL)

    async def stop_redis_listener(self) -> None:
        if self._redis_task is not None:
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass
            self._redis_task = None
        if self._redis_client is not None:
            await self._redis_client.aclose()
            self._redis_client = None

    async def _redis_loop(self) -> None:
        pubsub = self._redis_client.pubsub()
        await pubsub.subscribe(UI_EVENTS_REDIS_CHANNEL)
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    envelope = json.loads(message["data"])
                except json.JSONDecodeError as exc:
                    logger.error("Failed to parse UI envelope: %s", exc)
                    continue
                try:
                    await self._deliver_envelope(envelope)
                except Exception as exc:
                    logger.error("Failed to deliver UI envelope: %s", exc, exc_info=True)
        except asyncio.CancelledError:
            await pubsub.unsubscribe(UI_EVENTS_REDIS_CHANNEL)
            raise

    def get_stats(self) -> dict:
        return {
            "active_users": len(self._connections),
            "total_connections": sum(len(s) for s in self._connections.values()),
            "redis_connected": self._redis_client is not None,
            "redis_task_running": self._redis_task is not None and not self._redis_task.done(),
        }


notification_manager = NotificationManager()
