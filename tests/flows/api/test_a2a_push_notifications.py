"""
Тесты Push Notifications с реальным webhook сервером.

СТРОГАЯ ПРОВЕРКА соответствия a2a-sdk:
- Структура webhook payload проверяется
- Формат JSON-RPC 2.0 валидируется
- Все обязательные поля проверяются
"""

import asyncio
import time
import uuid
from typing import Any, Dict, List

import pytest
import pytest_asyncio
from aiohttp import web


def _msg(text: str, task_id: str = None, context_id: str = None) -> Dict[str, Any]:
    """Создаёт A2A Message с ОБЯЗАТЕЛЬНЫМИ полями."""
    m = {
        "messageId": str(uuid.uuid4()),
        "role": "user",
        "parts": [{"kind": "text", "text": text}],
    }
    if task_id:
        m["taskId"] = task_id
    if context_id:
        m["contextId"] = context_id
    return m


def _validate_webhook_payload(payload: Dict) -> None:
    """Строгая валидация webhook payload по A2A спецификации."""
    # JSON-RPC 2.0 структура
    assert "jsonrpc" in payload, "Webhook MUST have 'jsonrpc'"
    assert payload["jsonrpc"] == "2.0", "jsonrpc MUST be '2.0'"

    assert "method" in payload, "Webhook MUST have 'method'"
    assert payload["method"] == "tasks/pushNotification", \
        f"method MUST be 'tasks/pushNotification', got {payload['method']}"

    assert "params" in payload, "Webhook MUST have 'params'"

    params = payload["params"]

    # Обязательные поля в params
    assert "taskId" in params, "params MUST have 'taskId'"
    assert isinstance(params["taskId"], str), "taskId MUST be string"

    assert "contextId" in params, "params MUST have 'contextId'"
    assert isinstance(params["contextId"], str), "contextId MUST be string"

    assert "status" in params, "params MUST have 'status'"
    _validate_task_status(params["status"])

    assert "final" in params, "params MUST have 'final'"
    assert isinstance(params["final"], bool), "final MUST be boolean"


def _validate_task_status(status: Dict) -> None:
    """Строгая валидация TaskStatus."""
    assert "state" in status, "status MUST have 'state'"

    valid_states = [
        "submitted", "working", "input-required", "auth-required",
        "completed", "failed", "rejected", "canceled", "unknown"
    ]
    assert status["state"] in valid_states, f"Invalid state: {status['state']}"


def _validate_jsonrpc_response(data: Dict) -> None:
    """Строгая валидация JSON-RPC 2.0 response."""
    assert "jsonrpc" in data, "JSON-RPC response MUST have 'jsonrpc'"
    assert data["jsonrpc"] == "2.0", "jsonrpc MUST be '2.0'"
    assert "id" in data, "JSON-RPC response MUST have 'id'"
    assert "result" in data or "error" in data


class WebhookServer:
    """HTTP сервер для приёма webhooks с валидацией."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        self.host = host
        self.port = port
        self.received_webhooks: List[Dict[str, Any]] = []
        self.received_headers: List[Dict[str, str]] = []
        self._app = web.Application()
        self._app.router.add_post("/webhook", self._handle_webhook)
        self._app.router.add_post("/webhook/fail", self._handle_webhook_fail)
        self._runner = None
        self._site = None
        self._fail_count = 0
        self._fail_until = 0

    async def _handle_webhook(self, request: web.Request) -> web.Response:
        """Обработчик входящих webhooks."""
        data = await request.json()
        headers = dict(request.headers)
        self.received_webhooks.append(data)
        self.received_headers.append(headers)
        return web.json_response({"status": "ok"})

    async def _handle_webhook_fail(self, request: web.Request) -> web.Response:
        """Обработчик с настраиваемыми ошибками."""
        self._fail_count += 1
        if self._fail_count <= self._fail_until:
            return web.Response(status=500, text="Temporary failure")
        data = await request.json()
        self.received_webhooks.append(data)
        return web.json_response({"status": "ok"})

    def fail_first_n_requests(self, n: int):
        """Настроить сервер падать на первых N запросах."""
        self._fail_until = n
        self._fail_count = 0

    async def start(self) -> str:
        """Запускает сервер и возвращает URL."""
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()

        actual_port = self._site._server.sockets[0].getsockname()[1]
        self.port = actual_port

        return f"http://{self.host}:{actual_port}/webhook"

    async def stop(self):
        """Останавливает сервер."""
        if self._runner:
            await self._runner.cleanup()

    def clear(self):
        """Очищает полученные webhooks."""
        self.received_webhooks.clear()
        self.received_headers.clear()

    def get_url(self, path: str = "/webhook") -> str:
        """Возвращает URL для указанного пути."""
        return f"http://{self.host}:{self.port}{path}"


@pytest_asyncio.fixture
async def webhook_server():
    """Фикстура: поднимает webhook сервер."""
    server = WebhookServer()
    await server.start()
    yield server
    await server.stop()


class TestPushNotificationConfig:
    """Тесты CRUD операций с push notification конфигами."""

    @pytest.fixture
    async def flow_id(self, client):
        resp = await client.get("/flows/api/v1/registry/flows")
        agents = resp.json()
        if not agents:
            pytest.skip("No flows")
        return agents[0]["url"].split("/flows/")[-1]

    @pytest.mark.asyncio
    async def test_set_config_valid_structure(self, client, flow_id, webhook_server):
        """SET возвращает конфиг с правильной структурой."""
        task_id = str(uuid.uuid4())
        config_id = str(uuid.uuid4())
        webhook_url = webhook_server.get_url()

        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "tasks/pushNotificationConfig/set",
                "params": {
                    "taskId": task_id,
                    "pushNotificationConfig": {"id": config_id, "url": webhook_url},
                },
            },
        )

        data = resp.json()
        _validate_jsonrpc_response(data)

        result = data["result"]
        assert "pushNotificationConfig" in result

        config = result["pushNotificationConfig"]
        assert config["id"] == config_id
        assert config["url"] == webhook_url

    @pytest.mark.asyncio
    async def test_get_config_returns_same_data(self, client, flow_id, webhook_server):
        """GET возвращает те же данные что SET."""
        task_id = str(uuid.uuid4())
        config_id = str(uuid.uuid4())
        webhook_url = webhook_server.get_url()

        # SET
        await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "tasks/pushNotificationConfig/set",
                "params": {
                    "taskId": task_id,
                    "pushNotificationConfig": {"id": config_id, "url": webhook_url},
                },
            },
        )

        # GET
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "2",
                "method": "tasks/pushNotificationConfig/get",
                "params": {"id": task_id, "pushNotificationConfigId": config_id},
            },
        )

        data = resp.json()
        _validate_jsonrpc_response(data)

        config = data["result"]["pushNotificationConfig"]
        assert config["id"] == config_id
        assert config["url"] == webhook_url

    @pytest.mark.asyncio
    async def test_list_returns_all_configs(self, client, flow_id, webhook_server):
        """LIST возвращает все созданные конфиги в формате TaskPushNotificationConfig."""
        task_id = str(uuid.uuid4())
        webhook_url = webhook_server.get_url()

        # Создаём 3 конфига
        for i in range(3):
            await client.post(
                f"/flows/api/v1/{flow_id}",
                json={
                    "jsonrpc": "2.0",
                    "id": str(i),
                    "method": "tasks/pushNotificationConfig/set",
                    "params": {
                        "taskId": task_id,
                        "pushNotificationConfig": {"id": f"cfg-{i}", "url": webhook_url},
                    },
                },
            )

        # LIST
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "list",
                "method": "tasks/pushNotificationConfig/list",
                "params": {"id": task_id},
            },
        )

        data = resp.json()
        _validate_jsonrpc_response(data)

        configs = data["result"]
        assert isinstance(configs, list)
        assert len(configs) == 3

        # По A2A SDK: TaskPushNotificationConfig = {taskId, pushNotificationConfig}
        for config in configs:
            assert "taskId" in config, "TaskPushNotificationConfig MUST have 'taskId'"
            assert "pushNotificationConfig" in config, "TaskPushNotificationConfig MUST have 'pushNotificationConfig'"
            assert "id" in config["pushNotificationConfig"], "PushNotificationConfig MUST have 'id'"
            assert "url" in config["pushNotificationConfig"], "PushNotificationConfig MUST have 'url'"

        config_ids = {c["pushNotificationConfig"]["id"] for c in configs}
        assert config_ids == {"cfg-0", "cfg-1", "cfg-2"}

    @pytest.mark.asyncio
    async def test_delete_removes_config(self, client, flow_id, webhook_server):
        """DELETE удаляет конфиг."""
        task_id = str(uuid.uuid4())
        config_id = str(uuid.uuid4())
        webhook_url = webhook_server.get_url()

        # SET
        await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "tasks/pushNotificationConfig/set",
                "params": {
                    "taskId": task_id,
                    "pushNotificationConfig": {"id": config_id, "url": webhook_url},
                },
            },
        )

        # DELETE
        del_resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "2",
                "method": "tasks/pushNotificationConfig/delete",
                "params": {"id": task_id, "pushNotificationConfigId": config_id},
            },
        )

        data = del_resp.json()
        _validate_jsonrpc_response(data)
        assert data["result"] is None

        # GET должен вернуть null
        get_resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "3",
                "method": "tasks/pushNotificationConfig/get",
                "params": {"id": task_id, "pushNotificationConfigId": config_id},
            },
        )

        assert get_resp.json()["result"] is None

    @pytest.mark.asyncio
    async def test_config_with_authentication(self, client, flow_id, webhook_server):
        """Конфиг с authentication сохраняется."""
        task_id = str(uuid.uuid4())
        config_id = str(uuid.uuid4())
        webhook_url = webhook_server.get_url()

        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "tasks/pushNotificationConfig/set",
                "params": {
                    "taskId": task_id,
                    "pushNotificationConfig": {
                        "id": config_id,
                        "url": webhook_url,
                        "authentication": {
                            "schemes": ["bearer"],
                            "credentials": "secret-token",
                        },
                    },
                },
            },
        )

        data = resp.json()
        _validate_jsonrpc_response(data)

        config = data["result"]["pushNotificationConfig"]
        assert "authentication" in config


class TestPushNotificationWebhooks:
    """Тесты реальной отправки webhooks с СТРОГОЙ проверкой payload."""

    @pytest.fixture
    async def flow_id(self, client):
        resp = await client.get("/flows/api/v1/registry/flows")
        agents = resp.json()
        if not agents:
            pytest.skip("No flows")
        return agents[0]["url"].split("/flows/")[-1]

    @pytest.mark.asyncio
    async def test_webhook_on_completed_has_valid_structure(
        self, client, flow_id, mock_llm_with_queue, webhook_server, sync_tools
    ):
        """Webhook при completed имеет валидную A2A структуру."""
        mock_llm_with_queue([{"type": "text", "content": "Task done"}])

        task_id = str(uuid.uuid4())
        context_id = str(uuid.uuid4())
        config_id = str(uuid.uuid4())
        webhook_url = webhook_server.get_url()

        # Регистрируем webhook
        await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "tasks/pushNotificationConfig/set",
                "params": {
                    "taskId": task_id,
                    "pushNotificationConfig": {"id": config_id, "url": webhook_url},
                },
            },
        )

        # Выполняем задачу
        await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "2",
                "method": "message/send",
                "params": {"message": _msg("Execute", task_id, context_id)},
            },
        )

        # Ждём webhook
        for _ in range(20):
            await asyncio.sleep(0.5)
            if webhook_server.received_webhooks:
                break

        assert len(webhook_server.received_webhooks) > 0, "Webhook MUST be received"

        webhook = webhook_server.received_webhooks[-1]

        # СТРОГАЯ валидация
        _validate_webhook_payload(webhook)

        # Проверяем конкретные значения
        assert webhook["params"]["taskId"] == task_id
        assert webhook["params"]["status"]["state"] == "completed"
        assert webhook["params"]["final"] is True

    @pytest.mark.asyncio
    async def test_webhook_on_canceled_has_valid_structure(
        self, client, flow_id, mock_llm_with_queue, webhook_server, sync_tools
    ):
        """Webhook при canceled имеет валидную структуру."""
        mock_llm_with_queue([{"type": "text", "content": "Response"}])

        task_context_id = str(uuid.uuid4())
        config_id = str(uuid.uuid4())
        webhook_url = webhook_server.get_url()

        # Регистрируем webhook
        await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "tasks/pushNotificationConfig/set",
                "params": {
                    "taskId": task_context_id,
                    "pushNotificationConfig": {"id": config_id, "url": webhook_url},
                },
            },
        )

        # Создаём задачу
        await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "2",
                "method": "message/send",
                "params": {"message": _msg("Create", task_context_id, task_context_id)},
            },
        )

        webhook_server.clear()

        # Отменяем
        await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "3",
                "method": "tasks/cancel",
                "params": {"id": task_context_id},
            },
        )

        deadline = time.monotonic() + 8.0
        cancel_webhooks: list = []
        while time.monotonic() < deadline:
            cancel_webhooks = [
                w
                for w in webhook_server.received_webhooks
                if w.get("params", {}).get("status", {}).get("state") == "canceled"
            ]
            if cancel_webhooks:
                break
            await asyncio.sleep(0.05)

        assert len(cancel_webhooks) > 0, "Cancel webhook MUST be received"

        webhook = cancel_webhooks[0]
        _validate_webhook_payload(webhook)

        assert webhook["params"]["status"]["state"] == "canceled"
        assert webhook["params"]["final"] is True

    @pytest.mark.asyncio
    async def test_webhook_on_input_required_has_valid_structure(
        self, client, mock_llm_with_queue, webhook_server, sync_tools
    ):
        """Webhook при input-required имеет валидную структуру."""
        # Используем example_react т.к. он имеет ask_user tool
        flow_id = "example_react"
        mock_llm_with_queue([
            {"type": "tool_call", "tool": "ask_user", "args": {"question": "Name?"}},
        ])

        task_id = str(uuid.uuid4())
        context_id = str(uuid.uuid4())
        config_id = str(uuid.uuid4())
        webhook_url = webhook_server.get_url()

        # Регистрируем webhook
        await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "tasks/pushNotificationConfig/set",
                "params": {
                    "taskId": task_id,
                    "pushNotificationConfig": {"id": config_id, "url": webhook_url},
                },
            },
        )

        # Выполняем задачу с interrupt
        await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "2",
                "method": "message/send",
                "params": {"message": _msg("Start", task_id, context_id)},
            },
        )

        deadline = time.monotonic() + 8.0
        input_required_webhooks: list = []
        while time.monotonic() < deadline:
            input_required_webhooks = [
                w
                for w in webhook_server.received_webhooks
                if w.get("params", {}).get("status", {}).get("state") == "input-required"
            ]
            if input_required_webhooks:
                break
            await asyncio.sleep(0.05)

        assert len(input_required_webhooks) > 0, "Input-required webhook MUST be received"

        webhook = input_required_webhooks[0]
        _validate_webhook_payload(webhook)

        assert webhook["params"]["status"]["state"] == "input-required"
        assert webhook["params"]["final"] is True


class TestPushNotificationRetries:
    """Тесты retry механизма."""

    @pytest.fixture
    async def flow_id(self, client):
        resp = await client.get("/flows/api/v1/registry/flows")
        agents = resp.json()
        if not agents:
            pytest.skip("No flows")
        return agents[0]["url"].split("/flows/")[-1]

    @pytest.mark.asyncio
    async def test_task_completes_even_if_webhook_unavailable(
        self, client, flow_id, mock_llm_with_queue, sync_tools
    ):
        """Задача завершается даже если webhook недоступен."""
        mock_llm_with_queue([{"type": "text", "content": "Response"}])

        task_id = str(uuid.uuid4())
        context_id = str(uuid.uuid4())
        config_id = str(uuid.uuid4())

        # Webhook на несуществующий URL
        await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "tasks/pushNotificationConfig/set",
                "params": {
                    "taskId": task_id,
                    "pushNotificationConfig": {
                        "id": config_id,
                        "url": "http://127.0.0.1:59999/nonexistent",
                    },
                },
            },
        )

        # Выполняем задачу
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "2",
                "method": "message/send",
                "params": {"message": _msg("Test", task_id, context_id)},
            },
        )

        data = resp.json()
        _validate_jsonrpc_response(data)

        # Задача должна завершиться успешно
        assert data["result"]["status"]["state"] == "completed"


class TestPushNotificationEdgeCases:
    """Edge cases для push notifications."""

    @pytest.fixture
    async def flow_id(self, client):
        resp = await client.get("/flows/api/v1/registry/flows")
        agents = resp.json()
        if not agents:
            pytest.skip("No flows")
        return agents[0]["url"].split("/flows/")[-1]

    @pytest.mark.asyncio
    async def test_get_nonexistent_config_returns_null(self, client, flow_id):
        """GET несуществующего конфига возвращает null."""
        task_id = str(uuid.uuid4())
        config_id = str(uuid.uuid4())

        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "tasks/pushNotificationConfig/get",
                "params": {"id": task_id, "pushNotificationConfigId": config_id},
            },
        )

        data = resp.json()
        _validate_jsonrpc_response(data)
        assert data["result"] is None

    @pytest.mark.asyncio
    async def test_list_empty_returns_empty_array(self, client, flow_id):
        """LIST для задачи без конфигов возвращает []."""
        task_id = str(uuid.uuid4())

        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "tasks/pushNotificationConfig/list",
                "params": {"id": task_id},
            },
        )

        data = resp.json()
        _validate_jsonrpc_response(data)

        assert data["result"] == []

    @pytest.mark.asyncio
    async def test_delete_nonexistent_is_idempotent(self, client, flow_id):
        """DELETE несуществующего конфига - idempotent."""
        task_id = str(uuid.uuid4())
        config_id = str(uuid.uuid4())

        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "tasks/pushNotificationConfig/delete",
                "params": {"id": task_id, "pushNotificationConfigId": config_id},
            },
        )

        data = resp.json()
        _validate_jsonrpc_response(data)

        # DELETE должен быть успешным
        assert data["result"] is None

    @pytest.mark.asyncio
    async def test_update_config_overwrites(self, client, flow_id, webhook_server):
        """SET с тем же id перезаписывает конфиг."""
        task_id = str(uuid.uuid4())
        config_id = str(uuid.uuid4())
        webhook_url = webhook_server.get_url()

        # Создаём
        await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "tasks/pushNotificationConfig/set",
                "params": {
                    "taskId": task_id,
                    "pushNotificationConfig": {"id": config_id, "url": webhook_url},
                },
            },
        )

        # Обновляем
        new_url = f"{webhook_url}?updated=true"
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "2",
                "method": "tasks/pushNotificationConfig/set",
                "params": {
                    "taskId": task_id,
                    "pushNotificationConfig": {"id": config_id, "url": new_url},
                },
            },
        )

        data = resp.json()
        _validate_jsonrpc_response(data)

        assert data["result"]["pushNotificationConfig"]["url"] == new_url

        # GET должен вернуть обновлённый
        get_resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "3",
                "method": "tasks/pushNotificationConfig/get",
                "params": {"id": task_id, "pushNotificationConfigId": config_id},
            },
        )

        assert get_resp.json()["result"]["pushNotificationConfig"]["url"] == new_url
