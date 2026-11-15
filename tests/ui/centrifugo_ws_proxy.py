"""Прокси WS браузера UI E2E: dev-порт Centrifugo → тестовый инстанс.

`ws.effect.ts` на локальных dev-хостах (*.localhost, *.lvh.me) открывает
`ws://<host>:8000/connection/websocket` — dev-инстанс Centrifugo. Тестовый стек
держит свой Centrifugo (CENTRIFUGO_WS_URL, по умолчанию :19000) под тестовым
JWT-секретом. Прокси слушает :8000 на loopback и перенаправляет кадры на
тестовый endpoint — аналог ingress в проде, где `/realtime/connection/websocket`
ведёт на Centrifugo: реальное сетевое соединение, без перехвата протокола
Playwright (`route_web_socket`) и без подмены транспорта.

Прокси работает в отдельном daemon-потоке со своим event loop: будь он на
session-loop воркера pytest, занятый тестом loop голодал бы и WS-кадры
остальных xdist-воркеров вставали бы в очередь за его задачами.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from contextlib import suppress

import websockets
from websockets.asyncio.client import ClientConnection, connect
from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.http11 import Request, Response
from websockets.typing import Subprotocol

logger = logging.getLogger(__name__)

_LISTEN_PORT = 8000
_HEALTH_PATH = "/__ui_e2e_ws_health"
_HEALTH_BODY = "ui-e2e-centrifugo-ws-proxy"
_DEFAULT_UPSTREAM_URL = "ws://127.0.0.1:19000/connection/websocket"

_proxy_loop: asyncio.AbstractEventLoop | None = None
_proxy_server: Server | None = None
_proxy_thread: threading.Thread | None = None
_proxy_foreign_owned = False
_bind_done = threading.Event()
_bind_error: OSError | None = None


def _client_subprotocols(client: ServerConnection) -> list[Subprotocol]:
    """Субпротоколы из handshake клиента — прозрачно пробрасываются upstream."""
    raw = client.request.headers.get("Sec-WebSocket-Protocol", "")
    return [Subprotocol(v.strip()) for v in raw.split(",") if v.strip()]


async def _pump(
    source: ClientConnection | ServerConnection,
    sink: ClientConnection | ServerConnection,
) -> None:
    try:
        async for message in source:
            await sink.send(message)
    except websockets.ConnectionClosed:
        pass


async def _proxy_connection(client: ServerConnection, upstream_url: str) -> None:
    try:
        upstream = await connect(
            upstream_url,
            subprotocols=_client_subprotocols(client) or None,
            ping_interval=None,
            max_size=None,
        )
    except OSError as exc:
        logger.warning("ui e2e ws proxy: upstream %s unreachable: %s", upstream_url, exc)
        with suppress(websockets.ConnectionClosed):
            await client.close(1011, "test Centrifugo unreachable")
        return

    client_to_upstream = asyncio.create_task(_pump(client, upstream))
    upstream_to_client = asyncio.create_task(_pump(upstream, client))
    try:
        _, pending = await asyncio.wait(
            {client_to_upstream, upstream_to_client},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
    finally:
        await upstream.close()


def _maybe_health_response(
    connection: ServerConnection,
    request: Request,
) -> Response | None:
    """HTTP healthz на WS-порту — отличает наш прокси от чужого процесса."""
    if request.path == _HEALTH_PATH:
        return connection.respond(200, _HEALTH_BODY)
    return None


def _thread_main(upstream_url: str) -> None:
    """Тело daemon-потока прокси: свой event loop, независимый от воркера."""
    global _proxy_loop, _proxy_server, _bind_error

    async def _handle(client: ServerConnection) -> None:
        await _proxy_connection(client, upstream_url)

    async def _main() -> None:
        global _proxy_loop, _proxy_server, _bind_error
        _proxy_loop = asyncio.get_running_loop()
        try:
            # Только IPv4: bind «localhost» под гонкой воркеров
            # фрагментируется по семьям (::1 одному, 127.0.0.1 другому) —
            # проигравший raise-ит и закрывает свой частичный bind.
            # Браузер по Happy Eyeballs сам перебирает ::1 → 127.0.0.1.
            _proxy_server = await serve(
                _handle,
                "127.0.0.1",
                _LISTEN_PORT,
                select_subprotocol=lambda _conn, offered: offered[0] if offered else None,
                process_request=_maybe_health_response,
                ping_interval=None,
                max_size=None,
            )
        except OSError as exc:
            _bind_error = exc
            _bind_done.set()
            return
        logger.info("ui e2e ws proxy: localhost:%s → %s", _LISTEN_PORT, upstream_url)
        _bind_done.set()
        await _proxy_server.serve_forever()

    asyncio.run(_main())


async def _foreign_owner_holds_port() -> bool | None:
    """Состояние порта :8000: ``True`` — чужой (dev-стек, иной процесс),
    ``False`` — тестовый прокси слушает, ``None`` — никто не ответил
    (поток победившего воркера ещё поднимается).

    Проверяет обе loopback-семьи: winner мог забиндить только одну,
    когда вторая уже занята."""
    from httpx2 import AsyncClient

    answers: list[bool] = []
    for base_url in (
        f"http://127.0.0.1:{_LISTEN_PORT}",
        f"http://[::1]:{_LISTEN_PORT}",
    ):
        try:
            # trust_env=False: healthz loopback не должен уходить через
            # HTTP(S)_PROXY окружения — иначе ответ внешнего прокси
            # принимается за «чужого» владельца порта.
            async with AsyncClient(
                base_url=base_url, timeout=5.0, trust_env=False
            ) as http:
                resp = await http.get(_HEALTH_PATH)
            answers.append(
                resp.status_code != 200 or resp.text != _HEALTH_BODY
            )
        except Exception:
            continue
    if not answers:
        return None
    # Хотя бы одна семья ответила правильным healthz → это тестовый
    # прокси; все ответы чужие → владелец посторонний.
    return all(answers)


async def ensure_centrifugo_ws_proxy() -> None:
    """Идемпотентно поднимает прокси :8000 → тестовый Centrifugo.

    Порт общий для всех xdist-воркеров (браузеры всех воркеров ходят на
    `*.localhost:8000` → 127.0.0.1): первый воркер поднимает прокси в
    daemon-потоке, остальные проверяют healthz и переиспользуют его.
    """
    global _proxy_thread, _proxy_foreign_owned, _bind_error
    if _proxy_server is not None or _proxy_foreign_owned or _proxy_thread is not None:
        return
    upstream_url = os.environ.get("CENTRIFUGO_WS_URL", _DEFAULT_UPSTREAM_URL)
    _bind_done.clear()
    _bind_error = None
    _proxy_thread = threading.Thread(
        target=_thread_main,
        args=(upstream_url,),
        daemon=True,
        name="ui-e2e-centrifugo-ws-proxy",
    )
    _proxy_thread.start()

    # Ждём либо свой bind, либо healthz прокси другого воркера — в
    # daemon-потоке он не зависит от занятости наших asyncio-loop'ов.
    deadline = asyncio.get_running_loop().time() + 30
    while True:
        if _bind_done.is_set() and _bind_error is None:
            return
        healthz = await _foreign_owner_holds_port()
        if healthz is False:
            _proxy_foreign_owned = True
            return
        if (
            healthz is True
            or _bind_error is not None
            or asyncio.get_running_loop().time() > deadline
        ):
            raise RuntimeError(
                f"UI E2E: localhost:{_LISTEN_PORT} занят процессом, который не "
                "отвечает как тестовый Centrifugo-прокси — остановите dev-стек "
                "(make app) и перезапустите тесты"
            ) from _bind_error
        await asyncio.sleep(0.2)


async def stop_centrifugo_ws_proxy() -> None:
    """Гасит прокси, если его держит поток этого процесса."""
    global _proxy_server, _proxy_loop
    if _proxy_server is None or _proxy_loop is None:
        return
    _proxy_loop.call_soon_threadsafe(_proxy_server.close)
    _proxy_server = None
    _proxy_loop = None
