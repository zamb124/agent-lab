"""
Тесты для A2A Client.
Используется реальный HTTP сервер.
"""

import asyncio
import pytest
from aiohttp import web

from core.clients import A2AClient, A2AClientError
from core.clients.a2a_client import _extract_task_status_message

from tests.fixtures.aiohttp_ephemeral import tcp_site_assigned_port


class TestA2AClient:
    """Тесты A2AClient с реальным HTTP сервером."""

    @pytest.fixture
    async def mock_agent_server(self):
        """Поднимает тестовый HTTP сервер, имитирующий A2A агента."""
        public = {"base": "http://127.0.0.1:0"}

        async def handle_agent_card(request):
            return web.json_response({
                "name": "Test Agent",
                "url": public["base"],
                "version": "1.0.0",
                "branches": [{"id": "default", "name": "Default Skill"}],
            })

        async def handle_send_task(request):
            data = await request.json()
            content = data["params"]["message"]["parts"][0]["text"]

            return web.json_response({
                "jsonrpc": "2.0",
                "id": data["id"],
                "result": {
                    "status": {"state": "completed"},
                    "artifacts": [
                        {"parts": [{"type": "text", "text": f"Echo: {content}"}]}
                    ],
                },
            })

        app = web.Application()
        app.router.add_get("/.well-known/agent-card.json", handle_agent_card)
        app.router.add_post("/", handle_send_task)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = tcp_site_assigned_port(site)
        public["base"] = f"http://127.0.0.1:{port}"

        yield public["base"]

        await runner.cleanup()

    @pytest.fixture
    async def error_server(self):
        """Сервер который возвращает ошибки."""

        async def handle_error(request):
            return web.json_response(
                {"jsonrpc": "2.0", "error": {"code": -32600, "message": "Bad request"}},
                status=200
            )

        async def handle_404(request):
            return web.Response(status=404, text="Not Found")

        app = web.Application()
        app.router.add_get("/.well-known/agent-card.json", handle_404)
        app.router.add_post("/", handle_error)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = tcp_site_assigned_port(site)
        base = f"http://127.0.0.1:{port}"

        yield base

        await runner.cleanup()

    @pytest.mark.asyncio
    async def test_get_agent_card_success(self, mock_agent_server):
        """Успешное получение agent-card."""
        client = A2AClient()
        result = await client.get_agent_card(mock_agent_server)

        assert result["name"] == "Test Agent"
        assert len(result["branches"]) == 1

    @pytest.mark.asyncio
    async def test_get_agent_card_not_found(self, error_server):
        """404 при запросе agent-card."""
        client = A2AClient()

        with pytest.raises(A2AClientError, match="Failed to get agent-card"):
            await client.get_agent_card(error_server)

    @pytest.mark.asyncio
    async def test_send_task_success(self, mock_agent_server):
        """Успешная отправка задачи."""
        client = A2AClient()
        result = await client.send_task(
            base_url=mock_agent_server,
            content="Hello world",
            session_id="test-session",
        )

        assert result["response"] == "Echo: Hello world"
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_send_task_with_skill_id(self, mock_agent_server):
        """Отправка с указанием branch_id."""
        client = A2AClient()
        result = await client.send_task(
            base_url=mock_agent_server,
            content="Test",
            branch_id="custom_skill",
        )

        assert "response" in result

    @pytest.mark.asyncio
    async def test_send_task_error_response(self, error_server):
        """A2A ошибка в ответе."""
        client = A2AClient()

        with pytest.raises(A2AClientError, match="A2A error"):
            await client.send_task(error_server, "Hello")

    @pytest.mark.asyncio
    async def test_check_health_success(self, mock_agent_server):
        """Агент доступен."""
        client = A2AClient()
        result = await client.check_health(mock_agent_server)

        assert result is True

    @pytest.mark.asyncio
    async def test_check_health_failure(self):
        """Агент недоступен."""
        client = A2AClient(timeout=1.0)
        result = await client.check_health("http://localhost:19999")

        assert result is False

    @pytest.mark.asyncio
    async def test_trailing_slash_normalized(self, mock_agent_server):
        """URL нормализуется."""
        client = A2AClient()
        result = await client.get_agent_card(f"{mock_agent_server}/")

        assert result["name"] == "Test Agent"

    def test_extract_task_status_message_nested_parts(self):
        """Текст ошибки из вложенного A2A message (parts/root), как в JSON-RPC result."""
        status = {
            "state": "failed",
            "message": {
                "parts": [
                    {"root": {"text": "httpx.ReadTimeout"}},
                ],
            },
        }
        assert _extract_task_status_message(status) == "httpx.ReadTimeout"

    def test_parse_a2a_response_failed_uses_nested_message(self):
        client = A2AClient()
        raw = {
            "result": {
                "status": {
                    "state": "failed",
                    "message": {
                        "parts": [
                            {"root": {"text": "stream stalled"}},
                        ],
                    },
                },
            },
        }
        with pytest.raises(A2AClientError, match="stream stalled"):
            client._parse_a2a_response(raw)
