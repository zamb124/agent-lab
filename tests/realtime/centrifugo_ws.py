"""Клиент Centrifugo JSON protocol для E2E-тестов user WS."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Any, cast
from uuid import uuid4

import websockets
from websockets.asyncio.client import ClientConnection

from core.types import JsonObject, require_json_object
from core.utils.tokens import get_token_service

CENTRIFUGO_WS_URL = os.environ.get(
    "CENTRIFUGO_WS_URL",
    "ws://127.0.0.1:19000/connection/websocket",
)


class CentrifugoWsClient:
    def __init__(self, connection: ClientConnection) -> None:
        self._connection = connection
        self._command_id = 0
        self._pending: dict[int, asyncio.Future[JsonObject]] = {}
        self._publications: asyncio.Queue[JsonObject] = asyncio.Queue()
        self._company_id: str | None = None

    def bind_company_id(self, company_id: str) -> None:
        if not company_id:
            raise ValueError("company_id is required for Centrifugo RPC")
        self._company_id = company_id

    def _next_id(self) -> int:
        self._command_id += 1
        return self._command_id

    async def _send(self, command: JsonObject) -> None:
        await self._connection.send(json.dumps(command))

    async def connect(self, token: str) -> JsonObject:
        command_id = self._next_id()
        future: asyncio.Future[JsonObject] = asyncio.get_running_loop().create_future()
        self._pending[command_id] = future
        await self._send({"id": command_id, "connect": {"token": token}})
        return await asyncio.wait_for(future, timeout=10.0)

    async def rpc(self, method: str, data: JsonObject) -> JsonObject:
        command_id = self._next_id()
        future: asyncio.Future[JsonObject] = asyncio.get_running_loop().create_future()
        self._pending[command_id] = future
        await self._send({"id": command_id, "rpc": {"method": method, "data": data}})
        return await asyncio.wait_for(future, timeout=60.0)

    async def recv_platform_event(self, *, timeout: float = 10.0) -> JsonObject:
        return await asyncio.wait_for(self._publications.get(), timeout=timeout)

    def _resolve_reply(self, reply_id: int, frame: JsonObject) -> None:
        future = self._pending.pop(reply_id)
        error = frame.get("error")
        if error is not None:
            future.set_exception(RuntimeError(f"Centrifugo command error: {error}"))
            return
        future.set_result(frame)

    async def pump_until_closed(self) -> None:
        async for raw in self._connection:
            for frame in _parse_frames(raw):
                if _maybe_pong(frame):
                    await self._send({"pong": {}})
                    continue
                reply_id = frame.get("id")
                if isinstance(reply_id, int) and reply_id in self._pending:
                    self._resolve_reply(reply_id, frame)
                    continue
                publication = _publication_data(frame)
                if publication is not None:
                    await self._publications.put(publication)


def _parse_frames(raw: str | bytes) -> list[JsonObject]:
    text = raw.decode() if isinstance(raw, bytes) else raw
    stripped = text.strip()
    if stripped == "":
        raise AssertionError("empty Centrifugo frame")
    if "\n" not in stripped:
        return _frames_from_parsed(json.loads(stripped))
    frames: list[JsonObject] = []
    for line in stripped.splitlines():
        line_stripped = line.strip()
        if line_stripped == "":
            continue
        frames.extend(_frames_from_parsed(json.loads(line_stripped)))
    if not frames:
        raise AssertionError("empty Centrifugo frame")
    return frames


def _frames_from_parsed(parsed: Any) -> list[JsonObject]:
    if isinstance(parsed, list):
        if not parsed:
            raise AssertionError("empty Centrifugo frame list")
        return [require_json_object(item, "centrifugo.ws.frame") for item in parsed]
    return [require_json_object(parsed, "centrifugo.ws.frame")]


def _maybe_pong(frame: JsonObject) -> bool:
    return "ping" in frame


def _publication_data(frame: JsonObject) -> JsonObject | None:
    push = frame.get("push")
    if not isinstance(push, dict):
        pub = frame.get("pub")
        if isinstance(pub, dict):
            data = pub.get("data")
            if isinstance(data, dict):
                return require_json_object(data, "centrifugo.pub.data")
        return None
    pub = push.get("pub")
    if not isinstance(pub, dict):
        return None
    data = pub.get("data")
    if not isinstance(data, dict):
        return None
    return require_json_object(data, "centrifugo.push.pub.data")


@asynccontextmanager
async def connect_centrifugo(token: str) -> AsyncIterator[CentrifugoWsClient]:
    if not token:
        raise ValueError("SESSION JWT is required for Centrifugo connect")
    async with websockets.connect(CENTRIFUGO_WS_URL, max_size=8 * 1024 * 1024) as connection:
        client = CentrifugoWsClient(connection)
        pump = asyncio.create_task(client.pump_until_closed(), name="centrifugo.pump")
        try:
            token_data = get_token_service().validate_token(token)
            if token_data is None:
                raise ValueError("SESSION JWT is invalid for Centrifugo connect")
            client.bind_company_id(token_data.company_id)
            await client.connect(token)
            yield client
        finally:
            pump.cancel()
            try:
                await pump
            except (asyncio.CancelledError, websockets.exceptions.ConnectionClosed):
                pass


async def wait_platform_event(
    client: CentrifugoWsClient,
    *,
    type_: str,
    where: Mapping[str, Any] | None = None,
    meta_where: Mapping[str, Any] | None = None,
    timeout: float = 10.0,
) -> JsonObject:
    deadline = asyncio.get_running_loop().time() + timeout
    last_seen: list[str] = []
    while asyncio.get_running_loop().time() < deadline:
        remaining = deadline - asyncio.get_running_loop().time()
        event = await client.recv_platform_event(timeout=remaining)
        event_type = event.get("type")
        if not isinstance(event_type, str):
            continue
        last_seen.append(event_type)
        if event_type != type_:
            continue
        if where is not None:
            payload = event.get("payload")
            if not isinstance(payload, dict):
                continue
            matched = True
            for key, expected in where.items():
                if payload.get(key) != expected:
                    matched = False
                    break
            if not matched:
                continue
        if meta_where is not None:
            meta = event.get("meta")
            if not isinstance(meta, dict):
                continue
            matched_meta = True
            for key, expected in meta_where.items():
                if meta.get(key) != expected:
                    matched_meta = False
                    break
            if not matched_meta:
                continue
        return event
    raise AssertionError(
        f"wait_platform_event: type={type_!r} не получен; были: {last_seen}"
    )


async def assert_no_platform_event(
    client: CentrifugoWsClient,
    *,
    type_: str,
    duration: float = 1.5,
    where: Mapping[str, Any] | None = None,
) -> None:
    deadline = asyncio.get_running_loop().time() + duration
    while asyncio.get_running_loop().time() < deadline:
        remaining = deadline - asyncio.get_running_loop().time()
        try:
            event = await client.recv_platform_event(timeout=min(remaining, 0.4))
        except TimeoutError:
            continue
        event_type = event.get("type")
        if event_type != type_:
            continue
        if where is not None:
            payload = event.get("payload")
            if not isinstance(payload, dict):
                continue
            matched = True
            for key, expected in where.items():
                if payload.get(key) != expected:
                    matched = False
                    break
            if not matched:
                continue
        raise AssertionError(
            f"assert_no_platform_event: пришёл {type_!r} payload={event.get('payload')!r}"
        )


async def connect_rejected(token: str | None) -> int:
    """Connect без валидного SESSION JWT. Возвращает код close Centrifugo."""
    async with websockets.connect(CENTRIFUGO_WS_URL) as connection:
        command: dict[str, object] = {"id": 1, "connect": {}}
        if token is not None:
            command["connect"] = {"token": token}
        try:
            await connection.send(json.dumps(command))
            raw = await asyncio.wait_for(connection.recv(), timeout=5.0)
        except websockets.exceptions.ConnectionClosed as closed:
            received = closed.rcvd
            if received is None:
                raise AssertionError("Centrifugo close frame is required") from closed
            return received.code
    text = raw.decode() if isinstance(raw, bytes) else raw
    frame = json.loads(text)
    if not isinstance(frame, dict):
        raise AssertionError(f"Centrifugo reject frame must be object, got {frame!r}")
    if "error" in frame or "disconnect" in frame:
        error = frame.get("error")
        if isinstance(error, dict):
            code = error.get("code")
            if isinstance(code, int):
                return code
        disconnect = frame.get("disconnect")
        if isinstance(disconnect, dict):
            code = disconnect.get("code")
            if isinstance(code, int):
                return code
        return 3501
    raise AssertionError(f"Centrifugo accepted invalid token: {frame}")


async def rpc_platform_event(
    client: CentrifugoWsClient,
    *,
    event_type: str,
    payload: JsonObject,
    company_id: str,
    event_id: str | None = None,
    namespace: str = "default",
) -> JsonObject:
    command_id = event_id if event_id is not None else f"e_{uuid4().hex}"
    event: JsonObject = {
        "event_id": command_id,
        "type": event_type,
        "company_id": company_id,
        "payload": payload,
        "meta": {
            "source": "ws",
            "causation_id": command_id,
            "namespace": namespace,
        },
    }
    reply = await client.rpc("platform.event", event)
    rpc_body = reply.get("rpc")
    if not isinstance(rpc_body, dict):
        raise AssertionError(f"Centrifugo rpc reply missing rpc: {reply}")
    return require_json_object(cast(object, rpc_body.get("data")), "centrifugo.rpc.data")
