"""Локальный HTTP server для webhook notify + Telegram Bot API stubs (без mock)."""

from __future__ import annotations

import asyncio
import socket
from typing import Any

import pytest_asyncio
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from granian.server.embed import Server as GranianEmbedServer


class NotificationServer:
    """Реальный HTTP сервер для приёма уведомлений и stub Telegram API."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        self.host = host
        self.port = port
        self.received_requests: list[dict[str, Any]] = []
        self._app = FastAPI()
        self._app.add_api_route("/notify", self._handle_notify, methods=["POST"])
        self._app.add_api_route(
            "/telegram/{token}/getMe", self._handle_telegram_get_me, methods=["GET"]
        )
        self._app.add_api_route(
            "/telegram/{token}/setWebhook", self._handle_telegram_set_webhook, methods=["POST"]
        )
        self._app.add_api_route(
            "/telegram/{token}/deleteWebhook",
            self._handle_telegram_delete_webhook,
            methods=["POST"],
        )
        self._app.add_api_route(
            "/telegram/{token}/sendMessage", self._handle_telegram_send_message, methods=["POST"]
        )
        self._app.add_api_route(
            "/telegram/{token}/sendPhoto", self._handle_telegram_send_photo, methods=["POST"]
        )
        self._app.add_api_route(
            "/telegram/{token}/sendDocument", self._handle_telegram_send_document, methods=["POST"]
        )
        self._app.add_api_route(
            "/telegram/{token}/sendMessageDraft",
            self._handle_telegram_send_message_draft,
            methods=["POST"],
        )
        self._server: GranianEmbedServer | None = None
        self._server_task: asyncio.Task[None] | None = None

    async def _handle_notify(self, request: Request) -> JSONResponse:
        data = await request.json()
        headers = dict(request.headers)
        self.received_requests.append({"type": "notify", "data": data, "headers": headers})
        return JSONResponse({"status": "ok"})

    async def _handle_telegram_get_me(self, token: str) -> JSONResponse:
        self.received_requests.append({"type": "telegram_get_me", "token": token})
        return JSONResponse(
            {
                "ok": True,
                "result": {
                    "id": 42,
                    "is_bot": True,
                    "first_name": "TestBot",
                    "username": "test_bot",
                },
            }
        )

    async def _handle_telegram_set_webhook(self, token: str, request: Request) -> JSONResponse:
        data = await request.json()
        self.received_requests.append(
            {"type": "telegram_set_webhook", "token": token, "data": data}
        )
        return JSONResponse({"ok": True, "result": True, "description": "Webhook was set"})

    async def _handle_telegram_delete_webhook(self, token: str, request: Request) -> JSONResponse:
        data = await request.json()
        self.received_requests.append(
            {"type": "telegram_delete_webhook", "token": token, "data": data}
        )
        return JSONResponse({"ok": True, "result": True, "description": "Webhook was deleted"})

    async def _handle_telegram_send_message(self, token: str, request: Request) -> JSONResponse:
        data = await request.json()
        self.received_requests.append(
            {"type": "telegram_send_message", "token": token, "data": data}
        )
        return JSONResponse(
            {
                "ok": True,
                "result": {
                    "message_id": 12345,
                    "chat": {"id": data.get("chat_id")},
                    "text": data.get("text"),
                },
            }
        )

    async def _handle_telegram_send_photo(self, token: str, request: Request) -> JSONResponse:
        data = await request.json()
        self.received_requests.append({"type": "telegram_send_photo", "token": token, "data": data})
        return JSONResponse({"ok": True, "result": {"message_id": 12346}})

    async def _handle_telegram_send_document(self, token: str, request: Request) -> JSONResponse:
        data = await request.json()
        self.received_requests.append(
            {"type": "telegram_send_document", "token": token, "data": data}
        )
        return JSONResponse({"ok": True, "result": {"message_id": 12347}})

    async def _handle_telegram_send_message_draft(
        self, token: str, request: Request
    ) -> JSONResponse:
        data = await request.json()
        self.received_requests.append(
            {"type": "telegram_send_message_draft", "token": token, "data": data}
        )
        return JSONResponse({"ok": True, "result": True})

    async def start(self) -> str:
        if self.port == 0:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind((self.host, 0))
                self.port = sock.getsockname()[1]
        self._server = GranianEmbedServer(
            self._app, interface="asgi", address=self.host, port=self.port
        )
        self._server_task = asyncio.create_task(self._server.serve())
        for _ in range(100):
            try:
                reader, writer = await asyncio.open_connection(self.host, self.port)
                writer.close()
                await writer.wait_closed()
                break
            except OSError:
                await asyncio.sleep(0.05)
        else:
            raise RuntimeError(f"granian embed server не поднялся на {self.host}:{self.port}")
        return f"http://{self.host}:{self.port}"

    async def stop(self) -> None:
        if self._server is None:
            return
        self._server.stop()
        if self._server_task is not None:
            await self._server_task

    def clear(self) -> None:
        self.received_requests.clear()

    def get_requests(self, request_type: str | None = None) -> list[dict[str, Any]]:
        if request_type:
            return [req for req in self.received_requests if req["type"] == request_type]
        return self.received_requests


@pytest_asyncio.fixture
async def notification_server():
    """Фикстура: поднимает notification сервер."""
    server = NotificationServer()
    base_url = await server.start()
    yield (server, base_url)
    await server.stop()
