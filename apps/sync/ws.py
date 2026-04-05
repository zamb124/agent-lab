"""WebSocket endpoint realtime слоя Sync."""

from __future__ import annotations

import asyncio
import json

import redis.asyncio as redis
from fastapi import WebSocket, WebSocketDisconnect
from taskiq.exceptions import TaskiqResultTimeoutError

from core.config import get_settings
from apps.sync.realtime.commands import CallSignalPayload, CommandEnvelope, WsCommandFrame, WsResultFrame
from apps.sync.realtime.events import event_call_signal, event_user_presence
from apps.sync.realtime.publish_events import publish_realtime_events
from apps.sync.realtime.tasks import handle_command
from apps.sync.ws_presence import (
    clear_sync_ws_presence,
    refresh_sync_ws_presence,
    set_last_seen_now,
)
from core.websocket.auth import get_user_from_websocket
from core.logging import get_logger

logger = get_logger(__name__)

_ROUTING_KEYS = frozenset({"company_id", "recipient_user_ids"})


def _realtime_event_for_client(raw: dict) -> dict:
    return {k: v for k, v in raw.items() if k not in _ROUTING_KEYS}


async def deliver_realtime_event_to_websockets(manager: "ConnectionManager", raw: dict) -> None:
    company_id = raw.get("company_id")
    if not isinstance(company_id, str) or company_id == "":
        raise RuntimeError("sync realtime: событие без company_id.")
    client_payload = _realtime_event_for_client(raw)
    recipients = raw.get("recipient_user_ids")
    if recipients is None:
        await manager.broadcast_company(company_id, client_payload)
        return
    if not isinstance(recipients, list):
        raise RuntimeError("recipient_user_ids должен быть list или null.")
    for uid in recipients:
        if not isinstance(uid, str) or uid == "":
            raise RuntimeError("recipient_user_ids: ожидался непустой user_id.")
        await manager.send_to_company_user(company_id, uid, client_payload)


class ConnectionManager:
    """WebSocket по паре (company_id, user_id): изоляция тенантов и адресная доставка."""

    def __init__(self) -> None:
        self._by_company_user: dict[tuple[str, str], set[WebSocket]] = {}

    async def connect(self, company_id: str, user_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        key = (company_id, user_id)
        self._by_company_user.setdefault(key, set()).add(websocket)

    def disconnect(self, company_id: str, user_id: str, websocket: WebSocket) -> None:
        key = (company_id, user_id)
        ws_set = self._by_company_user.get(key)
        if ws_set is None:
            return
        ws_set.discard(websocket)
        if not ws_set:
            self._by_company_user.pop(key, None)

    async def send_to_company_user(self, company_id: str, user_id: str, payload: dict) -> None:
        key = (company_id, user_id)
        ws_set = self._by_company_user.get(key)
        if not ws_set:
            return
        text = json.dumps(payload, ensure_ascii=False)
        for ws in list(ws_set):
            try:
                await ws.send_text(text)
            except Exception:
                logger.exception(
                    "ws send_to_company_user failed: company_id=%s user_id=%s",
                    company_id,
                    user_id,
                )
                ws_set.discard(ws)
        if not ws_set:
            self._by_company_user.pop(key, None)

    async def broadcast_company(self, company_id: str, payload: dict) -> None:
        text = json.dumps(payload, ensure_ascii=False)
        for (cid, _uid), ws_set in list(self._by_company_user.items()):
            if cid != company_id:
                continue
            for ws in list(ws_set):
                try:
                    await ws.send_text(text)
                except Exception:
                    logger.exception("ws broadcast_company send failed: company_id=%s", company_id)
                    ws_set.discard(ws)
            if not ws_set:
                self._by_company_user.pop((cid, _uid), None)

    def connection_count(self, company_id: str, user_id: str) -> int:
        key = (company_id, user_id)
        ws_set = self._by_company_user.get(key)
        return len(ws_set) if ws_set else 0


manager = ConnectionManager()


class PubSubFanout:
    """Подписка на Redis Pub/Sub -> доставка на /sync/ws с учётом company и получателей."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._redis: redis.Redis | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        settings = get_settings()
        self._redis = redis.from_url(settings.database.redis_url)
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        task = self._task
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None
            if self._redis is not None:
                await self._redis.aclose()
                self._redis = None

    async def _run(self) -> None:
        r = self._redis
        if r is None:
            raise RuntimeError("Redis не инициализирован.")
        async with r.pubsub() as pubsub:
            await pubsub.subscribe("sync.realtime.events")
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=None)
                if message is None:
                    continue
                data_raw = message.get("data")
                if not isinstance(data_raw, (bytes, bytearray)):
                    raise RuntimeError("Некорректный тип pubsub message.data.")
                try:
                    event = json.loads(data_raw.decode("utf-8"))
                except Exception:
                    logger.exception("pubsub event decode failed")
                    continue
                try:
                    await deliver_realtime_event_to_websockets(manager, event)
                except Exception:
                    logger.exception("pubsub realtime deliver failed")


fanout = PubSubFanout()


async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint с auth через cookie (по образцу core/websocket/router.py)."""
    user = await get_user_from_websocket(websocket)
    if not user or not user.user_id:
        await websocket.close(code=1008, reason="Authentication required")
        logger.warning("ws sync: подключение отклонено — нет авторизации")
        return

    user_id = user.user_id
    company_id = user.active_company_id
    if not company_id or not isinstance(company_id, str):
        raise ValueError("active_company_id обязателен для Sync WebSocket.")
    settings = get_settings()
    redis_url = settings.database.redis_url
    if not redis_url:
        raise ValueError("database.redis_url не задан для sync WebSocket presence.")

    had_no_connections = manager.connection_count(company_id, user_id) == 0
    await manager.connect(company_id, user_id, websocket)
    await refresh_sync_ws_presence(redis_url, user_id)
    if had_no_connections:
        await publish_realtime_events(
            [
                event_user_presence(
                    company_id=company_id,
                    user_id=user_id,
                    online=True,
                    last_seen_at=None,
                ),
            ],
        )

    async def presence_heartbeat() -> None:
        interval = settings.ws_presence_heartbeat_interval_seconds
        while True:
            await asyncio.sleep(interval)
            await refresh_sync_ws_presence(redis_url, user_id)

    heartbeat_task = asyncio.create_task(presence_heartbeat())
    try:
        while True:
            raw = await websocket.receive_text()
            await refresh_sync_ws_presence(redis_url, user_id)
            frame = WsCommandFrame.model_validate_json(raw)
            logger.info("ws cmd received: user_id=%s id=%s type=%s", user_id, frame.id, frame.type)

            if frame.type == "call.signal":
                signal_payload = CallSignalPayload.model_validate(frame.payload)
                signal_event = event_call_signal(
                    signal_payload.call_id,
                    signal_payload.signal_type,
                    signal_payload.data,
                    company_id=company_id,
                    recipient_user_ids=[signal_payload.target_user_id],
                )
                signal_event.payload["target_user_id"] = signal_payload.target_user_id
                signal_event.payload["sender_user_id"] = user_id
                await publish_realtime_events([signal_event])
                out = WsResultFrame(id=frame.id, ok=True, result=None)
                await websocket.send_text(out.model_dump_json())
                continue

            cmd = CommandEnvelope(
                id=frame.id,
                actor_user_id=user_id,
                company_id=company_id,
                type=frame.type,
                payload=frame.payload,
            )
            task = await handle_command.kiq(cmd.model_dump())
            logger.info("ws cmd queued: id=%s", frame.id)

            try:
                res = await task.wait_result(
                    timeout=settings.sync_taskiq_wait_result_timeout_seconds,
                )
            except TaskiqResultTimeoutError as exc:
                logger.error("ws cmd timeout: id=%s", frame.id)
                out = WsResultFrame(
                    id=frame.id, ok=False, result=None,
                    error_code="timeout", error_detail=f"Task timeout: {exc.timeout}",
                )
                await websocket.send_text(out.model_dump_json())
                continue

            if res.is_err:
                logger.error("ws cmd failed: id=%s error=%s", frame.id, res.error)
                out = WsResultFrame(
                    id=frame.id, ok=False, result=None,
                    error_code="task_error", error_detail=str(res.error),
                )
            else:
                logger.info("ws cmd ok: id=%s", frame.id)
                out = WsResultFrame.model_validate({"id": frame.id, **res.return_value})

            await websocket.send_text(out.model_dump_json())

    except WebSocketDisconnect:
        pass
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        connections_before = manager.connection_count(company_id, user_id)
        manager.disconnect(company_id, user_id, websocket)
        if connections_before == 1:
            await clear_sync_ws_presence(redis_url, user_id)
            last_seen_iso = await set_last_seen_now(redis_url, user_id)
            await publish_realtime_events(
                [
                    event_user_presence(
                        company_id=company_id,
                        user_id=user_id,
                        online=False,
                        last_seen_at=last_seen_iso,
                    ),
                ],
            )
