"""Изолированные fixtures для тестов STT/TTS/VAD клиентов.

Переопределяет session-фикстуру ``setup_database_before_tests`` из корневого
``tests/conftest.py``: клиентские тесты не используют PostgreSQL, только
локальный ``aiohttp``. Без этого autouse в корне валит сборку при
недоступной тестовой БД.

Дополнительно можно запускать только этот пакет с ``--confcutdir=tests/clients``,
чтобы не подтягивать прочие хуки корневого conftest.
"""

from __future__ import annotations

import socket
import uuid
from typing import Any, AsyncIterator, Awaitable, Callable

import pytest
import pytest_asyncio
from aiohttp import web


@pytest.fixture(scope="session", autouse=True)
def setup_database_before_tests():
    """Пустышка: не гоняем Alembic/CREATE DATABASE для HTTP-клиентов."""
    yield


@pytest.fixture
def unique_id() -> str:
    return uuid.uuid4().hex[:12]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


HandlerFn = Callable[[web.Request], Awaitable[web.StreamResponse]]


class FakeSpeechServer:
    """Локальный HTTP-сервер для эмуляции STT/TTS/VAD HTTP-провайдеров."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self._handlers: dict[tuple[str, str], HandlerFn] = {}
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self.host: str = "127.0.0.1"
        self.port: int = 0

    def route(self, method: str, path: str, handler: HandlerFn) -> None:
        self._handlers[(method.upper(), path)] = handler

    @property
    def base_url(self) -> str:
        if self.port == 0:
            raise RuntimeError("FakeSpeechServer: server is not started")
        return f"http://{self.host}:{self.port}"

    async def start(self) -> None:
        app = web.Application()

        async def _dispatch(request: web.Request) -> web.StreamResponse:
            handler = self._handlers.get((request.method, request.path))
            if handler is None:
                return web.json_response(
                    {"error": "no handler", "method": request.method, "path": request.path},
                    status=404,
                )
            payload_record: dict[str, Any] = {
                "method": request.method,
                "path": request.path,
                "headers": dict(request.headers),
                "query": dict(request.query),
            }
            self.requests.append(payload_record)
            return await handler(request)

        app.router.add_route("*", "/{tail:.*}", _dispatch)

        self.port = _free_port()
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, host=self.host, port=self.port)
        await self._site.start()

    async def stop(self) -> None:
        if self._site is not None:
            await self._site.stop()
            self._site = None
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None


@pytest_asyncio.fixture
async def fake_speech_server() -> AsyncIterator[FakeSpeechServer]:
    server = FakeSpeechServer()
    await server.start()
    try:
        yield server
    finally:
        await server.stop()
