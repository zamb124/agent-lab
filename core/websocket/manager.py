"""
Менеджер WebSocket каналов платформы.

Источник UI-доставки — единая шина событий `platform:events`
(`core/events`). Менеджер читает live-хвост стрима (`PlatformEventTailReader`),
берёт события с непустым ``delivery``, проверяет адресацию
(user/company/broadcast) и форвардит сериализованное событие (без поля
``delivery``) в WS-сокеты адресатов.

Никакой бизнес-логики; никакой кастомной формы фрейма — фронту приходит
ровно `PlatformEvent` без ``delivery`` (event_id/type/company_id/payload/meta),
как в контракте `core/events/contract.py`.

Каждое доставленное событие логируется в request-лог-скоупе на основе
``meta.request_id`` и ``meta.trace_id`` события (если их нет —
генерируется уникальный ``ui-deliver:<uuid>``), чтобы факт пуша попадал
в общий поток событий запроса в Loki/Grafana.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Awaitable, Callable

from fastapi import WebSocket

from core.clients.redis_client import RedisClient
from core.config import get_settings
from core.events.consumer import PlatformEventTailReader
from core.events.contract import PlatformEvent
from core.logging import enter_request_scope, exit_request_scope, get_logger

logger = get_logger(__name__)

ConnectionHook = Callable[[str, str | None, bool], Awaitable[None]]


class NotificationManager:
    """Менеджер WebSocket-сокетов для всех сервисов платформы.

    Поддерживает регистрацию hooks (`register_connect_hook` /
    `register_disconnect_hook`) — сервис вызывает на `on_startup` и
    подписывается на события подключения/отключения, чтобы реализовать
    presence-tracking, online-статусы и т.п.
    """

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}
        self._socket_meta: dict[WebSocket, tuple[str, str | None, str]] = {}
        self._connection_lock: asyncio.Lock | None = None
        self._connection_lock_loop: asyncio.AbstractEventLoop | None = None
        self._tail_task: asyncio.Task[None] | None = None
        self._connect_hooks: list[ConnectionHook] = []
        self._disconnect_hooks: list[ConnectionHook] = []
        self._stats_redis: RedisClient | None = None
        self._stats_key: str | None = None
        self._stats_key_pattern: str | None = None

    def _get_connection_lock(self) -> asyncio.Lock:
        """Lock на текущий running loop (TestClient каждый раз поднимает свой)."""
        loop = asyncio.get_running_loop()
        if self._connection_lock is not None and self._connection_lock_loop is loop:
            return self._connection_lock
        self._connection_lock = asyncio.Lock()
        self._connection_lock_loop = loop
        return self._connection_lock

    def register_connect_hook(self, hook: ConnectionHook) -> None:
        """Hook вида ``async def hook(user_id: str, company_id: str | None, was_first_connection: bool) -> None``."""
        self._connect_hooks.append(hook)

    def register_disconnect_hook(self, hook: ConnectionHook) -> None:
        """Hook вида ``async def hook(user_id: str, company_id: str | None, was_last_connection: bool) -> None``."""
        self._disconnect_hooks.append(hook)

    async def connect(
        self,
        websocket: WebSocket,
        user_id: str,
        company_id: str | None = None,
    ) -> None:
        conn_id = uuid.uuid4().hex
        async with self._get_connection_lock():
            existing = self._connections.get(user_id)
            was_first_connection = not existing
            self._connections.setdefault(user_id, set()).add(websocket)
            self._socket_meta[websocket] = (user_id, company_id, conn_id)
            logger.info(
                "WS connected: user=%s company=%s total_for_user=%d",
                user_id,
                company_id,
                len(self._connections[user_id]),
            )
        await self._register_stats_connection(conn_id)
        for hook in self._connect_hooks:
            try:
                await hook(user_id, company_id, was_first_connection)
            except Exception:
                logger.exception("WS connect hook failed: user=%s", user_id)

    async def disconnect(self, websocket: WebSocket, user_id: str) -> None:
        was_last_connection = False
        company_id: str | None = None
        conn_id: str | None = None
        async with self._get_connection_lock():
            meta = self._socket_meta.pop(websocket, None)
            if meta is not None:
                _, company_id, conn_id = meta
            sockets = self._connections.get(user_id)
            if sockets is not None:
                sockets.discard(websocket)
                if not sockets:
                    _ = self._connections.pop(user_id, None)
                    was_last_connection = True
            logger.info("WS disconnected: user=%s last=%s", user_id, was_last_connection)
        if conn_id is not None:
            await self._unregister_stats_connection(conn_id)
        for hook in self._disconnect_hooks:
            try:
                await hook(user_id, company_id, was_last_connection)
            except Exception:
                logger.exception("WS disconnect hook failed: user=%s", user_id)

    def is_user_connected(self, user_id: str) -> bool:
        sockets = self._connections.get(user_id)
        return bool(sockets) and len(sockets) > 0

    async def _send_event_to_sockets(
        self,
        sockets: set[WebSocket],
        event_text: str,
        label: str,
    ) -> None:
        dead: set[WebSocket] = set()
        for ws in list(sockets):
            try:
                await ws.send_text(event_text)
            except Exception as exc:
                logger.warning("WS send failed (%s): %s", label, exc)
                dead.add(ws)
        if dead:
            dead_conn_ids: list[str] = []
            async with self._get_connection_lock():
                for ws in dead:
                    meta = self._socket_meta.pop(ws, None)
                    if meta:
                        uid, _, dead_conn_id = meta
                        bucket = self._connections.get(uid)
                        if bucket is not None:
                            bucket.discard(ws)
                            if not bucket:
                                _ = self._connections.pop(uid, None)
                        dead_conn_ids.append(dead_conn_id)
            for dead_conn_id in dead_conn_ids:
                await self._unregister_stats_connection(dead_conn_id)

    async def deliver_platform_event(self, event: PlatformEvent) -> None:
        """Доставить событие шины в сокеты адресата (`event.delivery`)."""
        delivery = event.delivery
        if delivery is None:
            return

        request_id = event.meta.request_id
        trace_id = event.meta.trace_id

        if not isinstance(request_id, str) or not request_id.strip():
            request_id = f"ui-deliver:{uuid.uuid4().hex}"
        if not isinstance(trace_id, str) or not trace_id.strip():
            trace_id = f"ui-deliver:{uuid.uuid4().hex}"

        settings = get_settings()
        scope_token = enter_request_scope(
            request_id=request_id,
            trace_id=trace_id,
            service_name=settings.server.name,
            ui_event_type=event.type,
            ui_event_id=event.event_id,
        )

        event_text = event.ws_frame_json()
        user_ids = delivery.user_ids
        company_id = delivery.company_id
        broadcast = delivery.broadcast

        try:
            if user_ids is not None:
                matched_users: set[WebSocket] = set()
                for user_id in user_ids:
                    matched_users.update(self._connections.get(user_id, set()))
                if not matched_users:
                    return
                await self._send_event_to_sockets(
                    matched_users, event_text, f"users={len(user_ids)}"
                )
                return

            if company_id is not None:
                matched: set[WebSocket] = set()
                for ws, (_uid, cid, _conn_id) in self._socket_meta.items():
                    if cid == company_id:
                        matched.add(ws)
                await self._send_event_to_sockets(matched, event_text, f"company={company_id}")
                return

            if broadcast:
                all_sockets: set[WebSocket] = set(self._socket_meta.keys())
                await self._send_event_to_sockets(all_sockets, event_text, "broadcast")
                return

            logger.warning("ui_event.target_invalid")
        finally:
            exit_request_scope(scope_token)

    async def start_redis_listener(self, redis_url: str) -> None:
        """Запустить tail-чтение шины `platform:events` для UI-доставки."""
        existing = self._tail_task
        if existing is not None:
            task_loop = existing.get_loop()
            if (
                not existing.done()
                and not task_loop.is_closed()
                and task_loop.is_running()
            ):
                logger.warning("Platform events tail listener already running")
                return
            # Задача с закрытого/чужого loop (pytest ASGI / reload) — перезапуск.
            self._tail_task = None
            if not existing.done() and not task_loop.is_closed():
                _ = existing.cancel()
            # Сокеты/lock с прошлого TestClient loop больше невалидны.
            self._connections.clear()
            self._socket_meta.clear()
            self._connection_lock = None
            self._connection_lock_loop = None
        await self._bind_stats_redis(redis_url)
        reader = PlatformEventTailReader(redis_url, self.deliver_platform_event)
        self._tail_task = asyncio.create_task(reader.run())
        logger.info("Platform events tail listener started")

    async def stop_redis_listener(self) -> None:
        """Остановить tail-чтение шины."""
        task = self._tail_task
        self._tail_task = None
        if task is None:
            return
        if not task.done():
            _ = task.cancel()
        try:
            await asyncio.wait_for(task, timeout=8.0)
        except asyncio.CancelledError:
            pass
        except asyncio.TimeoutError:
            logger.warning("notification_manager.tail_task_join_timed_out")
        except Exception as exc:
            logger.warning("notification_manager.tail_task_failed: %s", exc)
        await self._unbind_stats_redis()

    async def _bind_stats_redis(self, redis_url: str) -> None:
        await self._unbind_stats_redis()
        service_name = get_settings().server.name
        stats_key = f"platform:ws:conns:{service_name}:{os.getpid()}"
        stats_redis = RedisClient(redis_url)
        _ = await stats_redis.delete(stats_key)
        self._stats_redis = stats_redis
        self._stats_key = stats_key
        self._stats_key_pattern = f"platform:ws:conns:{service_name}:*"

    async def _unbind_stats_redis(self) -> None:
        stats_redis = self._stats_redis
        stats_key = self._stats_key
        self._stats_redis = None
        self._stats_key = None
        self._stats_key_pattern = None
        if stats_redis is None:
            return
        try:
            if stats_key is not None:
                _ = await stats_redis.delete(stats_key)
        finally:
            await stats_redis.close()

    async def _register_stats_connection(self, conn_id: str) -> None:
        stats_redis = self._stats_redis
        stats_key = self._stats_key
        if stats_redis is None or stats_key is None:
            return
        _ = await stats_redis.sadd(stats_key, conn_id)

    async def _unregister_stats_connection(self, conn_id: str) -> None:
        stats_redis = self._stats_redis
        stats_key = self._stats_key
        if stats_redis is None or stats_key is None:
            return
        _ = await stats_redis.srem(stats_key, conn_id)

    async def get_stats(self) -> dict[str, int | bool]:
        local_users = len(self._connections)
        local_conns = sum(len(sockets) for sockets in self._connections.values())
        total_connections = local_conns
        stats_redis = self._stats_redis
        pattern = self._stats_key_pattern
        if stats_redis is not None and pattern is not None:
            total_connections = 0
            for key in await stats_redis.scan_keys(pattern):
                total_connections += len(await stats_redis.smembers(key))
        return {
            "active_users": local_users,
            "total_connections": total_connections,
            "tail_task_running": self._tail_task is not None and not self._tail_task.done(),
        }


notification_manager = NotificationManager()
