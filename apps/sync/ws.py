"""WebSocket endpoint realtime слоя Sync."""

from __future__ import annotations

import asyncio
import json

import redis.asyncio as redis
from fastapi import WebSocket, WebSocketDisconnect
from taskiq.exceptions import TaskiqResultTimeoutError

from apps.sync.config import get_sync_settings
from apps.sync.realtime.commands import CommandEnvelope, WsCommandFrame, WsResultFrame
from apps.sync.realtime.tasks import handle_command
from core.context import get_context
from core.logging import get_logger

logger = get_logger(__name__)


class ConnectionManager:
    """Управление WebSocket соединениями по user_id."""

    def __init__(self) -> None:
        self._by_user: dict[str, set[WebSocket]] = {}

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._by_user.setdefault(user_id, set()).add(websocket)

    def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        ws_set = self._by_user.get(user_id)
        if ws_set is None:
            return
        ws_set.discard(websocket)
        if not ws_set:
            self._by_user.pop(user_id, None)

    async def send_to_user(self, user_id: str, payload: dict) -> None:
        ws_set = self._by_user.get(user_id)
        if not ws_set:
            return
        text = json.dumps(payload, ensure_ascii=False)
        for ws in list(ws_set):
            try:
                await ws.send_text(text)
            except Exception:
                logger.exception("ws send_to_user failed: user_id=%s", user_id)
                ws_set.discard(ws)
        if not ws_set:
            self._by_user.pop(user_id, None)

    async def broadcast(self, payload: dict) -> None:
        text = json.dumps(payload, ensure_ascii=False)
        for user_id, ws_set in list(self._by_user.items()):
            for ws in list(ws_set):
                try:
                    await ws.send_text(text)
                except Exception:
                    logger.exception("ws broadcast send failed: user_id=%s", user_id)
                    ws_set.discard(ws)
            if not ws_set:
                self._by_user.pop(user_id, None)


manager = ConnectionManager()


class PubSubFanout:
    """Подписка на Redis Pub/Sub -> broadcast всем WS клиентам."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._redis: redis.Redis | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        settings = get_sync_settings()
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
                    await manager.broadcast(event)
                except Exception:
                    logger.exception("pubsub broadcast failed")


fanout = PubSubFanout()


async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint с auth через платформу."""
    context = get_context()
    if not context or not context.user:
        await websocket.close(code=1008)
        return

    user_id = context.user.user_id
    company_id = context.active_company.company_id
    settings = get_sync_settings()

    try:
        await manager.connect(user_id, websocket)
        while True:
            raw = await websocket.receive_text()
            frame = WsCommandFrame.model_validate_json(raw)
            logger.info("ws cmd received: user_id=%s id=%s type=%s", user_id, frame.id, frame.type)

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
                res = await task.wait_result(timeout=settings.tasks.broker_url and 300.0 or 300.0)
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
        manager.disconnect(user_id, websocket)
