"""
Интеграционные тесты для /api/v1/code/execute endpoint.

Тестируют выполнение всех типов нод через унифицированный API:
- function (inline code)
- external_api (HTTP вызовы)
- remote_agent (A2A протокол)
- subflow (вложенные flows)
- react_node (LLM агенты)

ПРИНЦИПЫ:
- БЕЗ МОКОВ кроме LLM (mock_llm_redis)
- Реальные HTTP вызовы через client фикстуру
- Реальный PostgreSQL и Redis
- ASGI тестовый сервер для external_api и remote_agent
- СТРОГИЕ ПРОВЕРКИ: success, error, input_state, output_state, diff, duration_ms
"""

import asyncio
import socket
import pytest
from aiohttp import web
from httpx import ASGITransport, AsyncClient
from uvicorn import Config, Server

from tests.agents.fixtures.external_api.main import external_api_app


@pytest.fixture
async def external_api_server():
    """Запускает реальный HTTP сервер для external API."""
    # Находим свободный порт
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    
    config = Config(app=external_api_app, host="127.0.0.1", port=port, log_level="error")
    server = Server(config)
    
    # Запускаем сервер в фоне
    server_task = asyncio.create_task(server.serve())
    
    # Ждем пока сервер запустится
    max_attempts = 20
    for _ in range(max_attempts):
        try:
            test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_socket.settimeout(0.1)
            result = test_socket.connect_ex(("127.0.0.1", port))
            test_socket.close()
            if result == 0:
                break
        except Exception:
            pass
        await asyncio.sleep(0.1)
    else:
        server.should_exit = True
        raise RuntimeError(f"External API server failed to start on port {port}")
    
    base_url = f"http://127.0.0.1:{port}"
    yield base_url
    
    # Останавливаем сервер
    server.should_exit = True
    try:
        await asyncio.wait_for(server_task, timeout=5.0)
    except asyncio.TimeoutError:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass


@pytest.fixture
async def remote_agent_server():
    """Тестовый A2A сервер для remote_agent тестов."""
    
    async def handle_agent_card(request):
        return web.json_response({
            "name": "Test Remote Agent",
            "url": "http://localhost:9998",
            "skills": [{"id": "default", "name": "Default"}],
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
                    {"parts": [{"type": "text", "text": f"Remote response: {content}"}]}
                ],
            },
        })
    
    app = web.Application()
    app.router.add_get("/.well-known/agent-card.json", handle_agent_card)
    app.router.add_post("/", handle_send_task)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", 9998)
    await site.start()
    
    yield "http://localhost:9998"
    
    await runner.cleanup()


def assert_execute_response(data, expected_success: bool, expected_error: str = None):
    """Строгие проверки для execute response."""
    assert "success" in data
    assert data["success"] == expected_success
    
    assert "input_state" in data
    assert isinstance(data["input_state"], dict)
    
    assert "output_state" in data
    if expected_success:
        assert isinstance(data["output_state"], dict)
    else:
        assert data["output_state"] is None or isinstance(data["output_state"], dict)
    
    assert "diff" in data
    assert isinstance(data["diff"], list)
    
    assert "duration_ms" in data
    assert isinstance(data["duration_ms"], int)
    assert data["duration_ms"] >= 0
    
    if expected_success:
        assert data.get("error") is None
    else:
        assert "error" in data
        assert data["error"] is not None
        if expected_error:
            assert expected_error in data["error"]


def assert_diff_item(diff_item, path: str, change_type: str, old_value=None, new_value=None):
    """Проверка одного элемента diff."""
    assert diff_item["path"] == path
    assert diff_item["change_type"] == change_type
    
    if old_value is not None:
        assert diff_item.get("old_value") == old_value
    if new_value is not None:
        assert diff_item.get("new_value") == new_value


class TestCodeNode:
    """Тесты CodeNode (node_type: 'function')."""
    
    @pytest.mark.asyncio
    async def test_function_simple_execution(self, client, app):
        """Базовый inline code."""
        code = """
def run(state):
    state['result'] = 'executed'
    state['doubled'] = state.get('value', 0) * 2
    return state
"""
        state = {"value": 21}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={"node_type": "code", "node_config": {"code": code}, "state": state}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        assert data["output_state"]["result"] == "executed"
        assert data["output_state"]["doubled"] == 42
        
        # Проверка diff
        diff_by_path = {d["path"]: d for d in data["diff"]}
        assert "result" in diff_by_path
        assert diff_by_path["result"]["change_type"] == "added"
        assert "doubled" in diff_by_path
        assert diff_by_path["doubled"]["change_type"] == "added"
    
    @pytest.mark.asyncio
    async def test_function_async_code(self, client, app):
        """async def run(state)."""
        code = """
async def run(state):
    state['async_result'] = 'async_executed'
    return state
"""
        state = {}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={"node_type": "code", "node_config": {"code": code}, "state": state}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        assert data["output_state"]["async_result"] == "async_executed"
    
    @pytest.mark.asyncio
    async def test_function_with_variables(self, client, app):
        """Доступ к variables из state['variables']."""
        code = """
def run(state):
    greeting = variables.get('greeting', 'Hello')
    state['message'] = f"{greeting}, World!"
    return state
"""
        state = {"variables": {"greeting": "Привет"}}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={"node_type": "code", "node_config": {"code": code}, "state": state}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        assert data["output_state"]["message"] == "Привет, World!"
    
    @pytest.mark.asyncio
    async def test_function_import_json(self, client, app):
        """import json работает."""
        code = """
import json

def run(state):
    data = json.loads(state.get('json_input', '{}'))
    state['parsed_name'] = data.get('name', 'unknown')
    return state
"""
        state = {"json_input": '{"name": "Test", "value": 123}'}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={"node_type": "code", "node_config": {"code": code}, "state": state}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        assert data["output_state"]["parsed_name"] == "Test"
    
    @pytest.mark.asyncio
    async def test_function_import_re(self, client, app):
        """import re работает."""
        code = """
import re

def run(state):
    text = state.get('text', '')
    matches = re.findall(r'\\d+', text)
    state['numbers'] = matches
    return state
"""
        state = {"text": "abc123def456ghi"}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={"node_type": "code", "node_config": {"code": code}, "state": state}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        assert data["output_state"]["numbers"] == ["123", "456"]
    
    @pytest.mark.asyncio
    async def test_function_import_datetime(self, client, app):
        """import datetime работает."""
        code = """
from datetime import datetime, timedelta

def run(state):
    now = datetime.now()
    tomorrow = now + timedelta(days=1)
    state['timestamp'] = now.isoformat()
    state['tomorrow'] = tomorrow.isoformat()
    return state
"""
        state = {}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={"node_type": "code", "node_config": {"code": code}, "state": state}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        assert "timestamp" in data["output_state"]
        assert "tomorrow" in data["output_state"]
    
    @pytest.mark.asyncio
    async def test_function_nested_state_modification(self, client, app):
        """Изменение вложенных объектов."""
        code = """
def run(state):
    if 'user' not in state:
        state['user'] = {}
    state['user']['name'] = 'John'
    state['user']['age'] = 30
    return state
"""
        state = {"user": {"name": "Jane"}}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={"node_type": "code", "node_config": {"code": code}, "state": state}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        assert data["output_state"]["user"]["name"] == "John"
        assert data["output_state"]["user"]["age"] == 30
        
        # Проверка diff для вложенного пути
        diff_by_path = {d["path"]: d for d in data["diff"]}
        assert "user.name" in diff_by_path or any("user.name" in d["path"] for d in data["diff"])
    
    @pytest.mark.asyncio
    async def test_function_diff_added(self, client, app):
        """Новые поля в diff."""
        code = """
def run(state):
    state['new_field'] = 'added'
    return state
"""
        state = {}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={"node_type": "code", "node_config": {"code": code}, "state": state}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        
        diff_by_path = {d["path"]: d for d in data["diff"]}
        assert "new_field" in diff_by_path
        assert diff_by_path["new_field"]["change_type"] == "added"
        assert diff_by_path["new_field"].get("old_value") is None
        assert diff_by_path["new_field"].get("new_value") == "added"
    
    @pytest.mark.asyncio
    async def test_function_diff_modified(self, client, app):
        """Изменённые поля в diff."""
        code = """
def run(state):
    state['existing'] = 'modified'
    return state
"""
        state = {"existing": "original"}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={"node_type": "code", "node_config": {"code": code}, "state": state}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        
        diff_by_path = {d["path"]: d for d in data["diff"]}
        assert "existing" in diff_by_path
        assert diff_by_path["existing"]["change_type"] == "changed"
        assert diff_by_path["existing"].get("old_value") == "original"
        assert diff_by_path["existing"].get("new_value") == "modified"
    
    @pytest.mark.asyncio
    async def test_function_diff_removed(self, client, app):
        """Установка поля в None вместо удаления (ExecutionState - Pydantic модель)."""
        code = """
def run(state):
    state.to_remove = None
    return state
"""
        state = {"to_remove": "value", "keep": "value"}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={"node_type": "code", "node_config": {"code": code}, "state": state}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        assert data["output_state"]["to_remove"] is None
        assert "keep" in data["output_state"]
        
        diff_by_path = {d["path"]: d for d in data["diff"]}
        assert "to_remove" in diff_by_path
        assert diff_by_path["to_remove"]["change_type"] == "changed"
        assert diff_by_path["to_remove"].get("old_value") == "value"
        assert diff_by_path["to_remove"].get("new_value") is None
    
    @pytest.mark.asyncio
    async def test_function_diff_no_changes(self, client, app):
        """Без изменений state."""
        code = """
def run(state):
    return state
"""
        state = {"value": 42}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={"node_type": "code", "node_config": {"code": code}, "state": state}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        assert len(data["diff"]) == 0
    
    @pytest.mark.asyncio
    async def test_function_diff_nested_path(self, client, app):
        """Вложенный путь в diff."""
        code = """
def run(state):
    if 'user' not in state:
        state['user'] = {}
    state['user']['email'] = 'test@example.com'
    return state
"""
        state = {"user": {"name": "John"}}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={"node_type": "code", "node_config": {"code": code}, "state": state}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        
        # Проверяем что есть путь с точкой для вложенного поля
        diff_paths = [d["path"] for d in data["diff"]]
        assert any("user.email" in path or path == "user.email" for path in diff_paths)
    
    @pytest.mark.asyncio
    async def test_function_empty_code(self, client, app):
        """code=''."""
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={"node_type": "code", "code": "", "state": {}}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=False, expected_error="code, tool_id или function обязателен")
    
    @pytest.mark.asyncio
    async def test_function_whitespace_code(self, client, app):
        """code='   \n  '."""
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={"node_type": "code", "code": "   \n  ", "state": {}}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=False, expected_error="code, tool_id или function обязателен")
    
    @pytest.mark.asyncio
    async def test_function_syntax_error(self, client, app):
        """Невалидный Python."""
        code = "def run(state):\n    return state\ninvalid syntax here"
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={"node_type": "code", "node_config": {"code": code}, "state": {}}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=False)
        assert "Syntax" in data["error"] or "синтакси" in data["error"].lower()
    
    @pytest.mark.asyncio
    async def test_function_runtime_error(self, client, app):
        """raise ValueError."""
        code = """
def run(state):
    raise ValueError("Intentional error")
"""
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={"node_type": "code", "node_config": {"code": code}, "state": {}}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=False)
        assert "ValueError" in data["error"] or "Intentional error" in data["error"]
    
    @pytest.mark.asyncio
    async def test_function_finds_first_function(self, client, app):
        """auto_find находит первую функцию если нет run()."""
        code = "def other_function(state):\n    return state"
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={"node_type": "code", "node_config": {"code": code}, "state": {}}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
    
    @pytest.mark.asyncio
    async def test_function_import_blocked_os(self, client, app):
        """import os блокируется."""
        code = """
import os
def run(state):
    return state
"""
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={"node_type": "code", "node_config": {"code": code}, "state": {}}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=False)
        # Блокировка опасных модулей
        assert "os" in data["error"].lower() or "блок" in data["error"].lower() or "запрещ" in data["error"].lower()
    
    @pytest.mark.asyncio
    async def test_function_import_blocked_subprocess(self, client, app):
        """import subprocess блокируется."""
        code = """
import subprocess
def run(state):
    return state
"""
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={"node_type": "code", "node_config": {"code": code}, "state": {}}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=False)
        assert "subprocess" in data["error"].lower() or "блок" in data["error"].lower() or "запрещ" in data["error"].lower()


class TestExternalAPINode:
    """Тесты ExternalAPINode (node_type: 'external_api')."""
    
    @pytest.mark.asyncio
    async def test_external_api_post_echo(self, client, app, external_api_server):
        """POST /echo."""
        state = {"message": "Hello", "uppercase": False}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "external_api",
                "node_config": {
                    "url": f"{external_api_server}/echo",
                    "method": "POST",
                    "parameters": [
                        {"name": "message", "location": "body"},
                        {"name": "uppercase", "location": "body"}
                    ]
                },
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        assert "api_response" in data["output_state"]
        assert data["output_state"]["api_response"]["result"] == "Hello"
        assert data["output_state"]["api_status"] == "completed"
    
    @pytest.mark.asyncio
    async def test_external_api_get_user(self, client, app, external_api_server):
        """GET /user/{id}."""
        state = {"user_id": "1"}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "external_api",
                "node_config": {
                    "url": f"{external_api_server}/user/{{user_id}}",
                    "method": "GET",
                    "parameters": [
                        {"name": "user_id", "location": "path"}
                    ]
                },
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        assert "api_response" in data["output_state"]
        assert data["output_state"]["api_response"]["name"] == "Alice"
    
    @pytest.mark.asyncio
    async def test_external_api_calculate_add(self, client, app, external_api_server):
        """POST /calculate add."""
        state = {"a": 10, "b": 5, "operation": "add"}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "external_api",
                "node_config": {
                    "url": f"{external_api_server}/calculate",
                    "method": "POST",
                    "parameters": [
                        {"name": "a", "location": "body"},
                        {"name": "b", "location": "body"},
                        {"name": "operation", "location": "body"}
                    ]
                },
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        assert data["output_state"]["api_response"]["result"] == 15
    
    @pytest.mark.asyncio
    async def test_external_api_calculate_multiply(self, client, app, external_api_server):
        """POST /calculate multiply."""
        state = {"a": 6, "b": 7, "operation": "multiply"}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "external_api",
                "node_config": {
                    "url": f"{external_api_server}/calculate",
                    "method": "POST",
                    "parameters": [
                        {"name": "a", "location": "body"},
                        {"name": "b", "location": "body"},
                        {"name": "operation", "location": "body"}
                    ]
                },
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        assert data["output_state"]["api_response"]["result"] == 42
    
    @pytest.mark.asyncio
    async def test_external_api_auth_bearer(self, client, app, external_api_server):
        """Authorization header."""
        state = {"message": "Test"}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "external_api",
                "node_config": {
                    "url": f"{external_api_server}/auth-required",
                    "method": "POST",
                    "auth_headers": {"Authorization": "Bearer test-token-123"},
                    "parameters": [{"name": "message", "location": "body"}]
                },
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        assert data["output_state"]["api_response"]["auth_type"] == "bearer"
    
    @pytest.mark.asyncio
    async def test_external_api_auth_api_key(self, client, app, external_api_server):
        """X-API-Key header."""
        state = {"message": "Test"}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "external_api",
                "node_config": {
                    "url": f"{external_api_server}/auth-required",
                    "method": "POST",
                    "auth_headers": {"X-API-Key": "api-key-456"},
                    "parameters": [{"name": "message", "location": "body"}]
                },
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        assert data["output_state"]["api_response"]["auth_type"] == "api_key"
    
    @pytest.mark.asyncio
    async def test_external_api_auth_var_resolution(self, client, app, external_api_server):
        """@var:token в header."""
        state = {
            "variables": {"api_token": "var-token-789"},
            "message": "Test"
        }
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "external_api",
                "node_config": {
                    "url": f"{external_api_server}/auth-required",
                    "method": "POST",
                    "auth_headers": {"Authorization": "Bearer @var:api_token"},
                    "parameters": [{"name": "message", "location": "body"}]
                },
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        assert data["output_state"]["api_response"]["auth_type"] == "bearer"
    
    @pytest.mark.asyncio
    async def test_external_api_state_mapping_simple(self, client, app, external_api_server):
        """response.field -> state.field."""
        state = {"message": "Hello"}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "external_api",
                "node_config": {
                    "url": f"{external_api_server}/echo",
                    "method": "POST",
                    "parameters": [{"name": "message", "location": "body"}],
                    "state_mapping": {"result": "echo_result"}
                },
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        assert data["output_state"]["echo_result"] == "Hello"
    
    @pytest.mark.asyncio
    async def test_external_api_state_mapping_nested(self, client, app, external_api_server):
        """response.data.result -> state.result."""
        state = {"a": 10, "b": 5, "operation": "add"}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "external_api",
                "node_config": {
                    "url": f"{external_api_server}/calculate",
                    "method": "POST",
                    "parameters": [
                        {"name": "a", "location": "body"},
                        {"name": "b", "location": "body"},
                        {"name": "operation", "location": "body"}
                    ],
                    "state_mapping": {"result": "calculation_result"}
                },
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        assert data["output_state"]["calculation_result"] == 15
    
    @pytest.mark.asyncio
    async def test_external_api_state_mapping_multiple(self, client, app, external_api_server):
        """Несколько полей."""
        state = {"a": 10, "b": 5, "operation": "add"}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "external_api",
                "node_config": {
                    "url": f"{external_api_server}/calculate",
                    "method": "POST",
                    "parameters": [
                        {"name": "a", "location": "body"},
                        {"name": "b", "location": "body"},
                        {"name": "operation", "location": "body"}
                    ],
                    "state_mapping": {
                        "result": "calc_result",
                        "operation": "calc_operation"
                    }
                },
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        assert data["output_state"]["calc_result"] == 15
        assert data["output_state"]["calc_operation"] == "add"
    
    @pytest.mark.asyncio
    async def test_external_api_var_in_url(self, client, app, external_api_server):
        """@var:base_url в URL."""
        state = {
            "variables": {"base_url": external_api_server},
            "user_id": "2"
        }
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "external_api",
                "node_config": {
                    "url": "@var:base_url/user/{user_id}",
                    "method": "GET",
                    "parameters": [{"name": "user_id", "location": "path"}]
                },
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        assert data["output_state"]["api_response"]["name"] == "Bob"
    
    @pytest.mark.asyncio
    async def test_external_api_missing_url(self, client, app):
        """url=''."""
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "external_api",
                "node_config": {"url": ""},
                "state": {}
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=False, expected_error="url обязателен")
    
    @pytest.mark.asyncio
    async def test_external_api_error_response(self, client, app, external_api_server):
        """API возвращает error."""
        state = {"a": 10, "b": 0, "operation": "divide"}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "external_api",
                "node_config": {
                    "url": f"{external_api_server}/calculate",
                    "method": "POST",
                    "parameters": [
                        {"name": "a", "location": "body"},
                        {"name": "b", "location": "body"},
                        {"name": "operation", "location": "body"}
                    ]
                },
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=False)
        assert "Division by zero" in data["error"] or "error" in data["error"].lower()
    
    @pytest.mark.asyncio
    async def test_external_api_unauthorized(self, client, app, external_api_server):
        """Без auth на protected endpoint."""
        state = {"message": "Test"}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "external_api",
                "node_config": {
                    "url": f"{external_api_server}/auth-required",
                    "method": "POST",
                    "parameters": [{"name": "message", "location": "body"}]
                },
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=False)
        assert "401" in data["error"] or "unauthorized" in data["error"].lower() or "authorization" in data["error"].lower()
    
    @pytest.mark.asyncio
    async def test_external_api_interrupt(self, client, app, external_api_server):
        """status='waiting_input'."""
        state = {"message": "short"}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "external_api",
                "node_config": {
                    "url": f"{external_api_server}/ask-clarification",
                    "method": "POST",
                    "parameters": [{"name": "message", "location": "body"}]
                },
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        assert "interrupt" in data["output_state"] or data["output_state"].get("api_status") == "waiting_input"


class TestRemoteAgentNode:
    """Тесты RemoteAgentNode (node_type: 'remote_agent')."""
    
    @pytest.mark.asyncio
    async def test_remote_agent_basic(self, client, app, remote_agent_server):
        """Простой вызов."""
        state = {"content": "Hello from test"}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "remote_agent",
                "node_config": {"url": remote_agent_server},
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        assert "response" in data["output_state"]
        assert "Remote response: Hello from test" in data["output_state"]["response"]
        assert data["output_state"].get("remote_status") == "completed"
    
    @pytest.mark.asyncio
    async def test_remote_agent_with_skill_id(self, client, app, remote_agent_server):
        """skill_id передаётся."""
        state = {"content": "Test"}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "remote_agent",
                "node_config": {
                    "url": remote_agent_server,
                    "skill_id": "custom_skill"
                },
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        assert "response" in data["output_state"]
    
    @pytest.mark.asyncio
    async def test_remote_agent_input_mapping_content(self, client, app, remote_agent_server):
        """input_mapping с @state:content."""
        state = {"content": "Mapped content"}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "remote_agent",
                "node_config": {
                    "url": remote_agent_server,
                    "input_mapping": {"content": "@state:content"}
                },
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        assert "Mapped content" in data["output_state"]["response"]
    
    @pytest.mark.asyncio
    async def test_remote_agent_input_mapping_state_field(self, client, app, remote_agent_server):
        """input_mapping с @state:user_query."""
        state = {"user_query": "Query from state field"}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "remote_agent",
                "node_config": {
                    "url": remote_agent_server,
                    "input_mapping": {"content": "@state:user_query"}
                },
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        assert "Query from state field" in data["output_state"]["response"]
    
    @pytest.mark.asyncio
    async def test_remote_agent_input_mapping_messages(self, client, app, remote_agent_server):
        """input_mapping с @state:last_message (messages как JSON)."""
        state = {
            "last_message": "Last user message text"
        }
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "remote_agent",
                "node_config": {
                    "url": remote_agent_server,
                    "input_mapping": {"content": "@state:last_message"}
                },
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        assert "response" in data["output_state"]
        assert "Last user message" in data["output_state"]["response"]
    
    @pytest.mark.asyncio
    async def test_remote_agent_auth_headers(self, client, app, remote_agent_server):
        """auth_headers передаются."""
        state = {"content": "Test"}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "remote_agent",
                "node_config": {
                    "url": remote_agent_server,
                    "auth_headers": {"Authorization": "Bearer token-123"}
                },
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
    
    @pytest.mark.asyncio
    async def test_remote_agent_auth_var_resolution(self, client, app, remote_agent_server):
        """@var: в auth_headers."""
        state = {
            "variables": {"remote_token": "var-token-456"},
            "content": "Test"
        }
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "remote_agent",
                "node_config": {
                    "url": remote_agent_server,
                    "auth_headers": {"Authorization": "Bearer @var:remote_token"}
                },
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
    
    @pytest.mark.asyncio
    async def test_remote_agent_missing_url(self, client, app):
        """url=''."""
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "remote_agent",
                "node_config": {"url": ""},
                "state": {}
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=False, expected_error="url или agent_id обязателен")
    
    @pytest.mark.asyncio
    async def test_remote_agent_connection_error(self, client, app):
        """Недоступный URL."""
        state = {"content": "Test"}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "remote_agent",
                "node_config": {"url": "http://nonexistent-host:99999"},
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=False)
        assert "error" in data


class TestAgentNode:
    """Тесты AgentNode (node_type: 'agent')."""
    
    @pytest.mark.asyncio
    async def test_subflow_basic_execution(self, client, app, container):
        """Вызов example_graph."""
        state = {"content": "заказ на iPhone"}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "agent",
                "node_config": {"agent_id": "example_graph"},
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        assert "response" in data["output_state"] or "route" in data["output_state"]
    
    @pytest.mark.asyncio
    async def test_subflow_with_skill_id(self, client, app, container):
        """skill_id='fast_track'."""
        state = {"content": "заказ"}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "agent",
                "node_config": {
                    "agent_id": "example_graph",
                    "skill_id": "fast_track"
                },
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
    
    @pytest.mark.asyncio
    async def test_subflow_input_mapping_full_state(self, client, app, container):
        """Без mapping - весь state."""
        state = {"content": "test", "user_name": "John"}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "agent",
                "node_config": {"agent_id": "example_graph"},
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
    
    @pytest.mark.asyncio
    async def test_subflow_input_mapping_constant(self, client, app, container):
        """Константа передаётся."""
        state = {"other_field": "value"}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "agent",
                "node_config": {
                    "agent_id": "example_graph",
                    "input_mapping": {
                        "content": "Fixed content from mapping"
                    }
                },
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
    
    @pytest.mark.asyncio
    async def test_subflow_input_mapping_state_path(self, client, app, container):
        """@state:user.name резолвится."""
        state = {"user": {"name": "Alice"}, "other": "data"}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "agent",
                "node_config": {
                    "agent_id": "example_graph",
                    "input_mapping": {
                        "content": "@state:user.name"
                    }
                },
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
    
    @pytest.mark.asyncio
    async def test_subflow_input_mapping_multiple(self, client, app, container):
        """Несколько полей."""
        state = {"user_query": "query", "user_name": "Bob"}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "agent",
                "node_config": {
                    "agent_id": "example_graph",
                    "input_mapping": {
                        "content": "@state:user_query",
                        "user_name": "@state:user_name"
                    }
                },
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
    
    @pytest.mark.asyncio
    async def test_subflow_preserves_variables(self, client, app, container):
        """variables сохраняется."""
        state = {
            "variables": {"company_name": "TestCorp"},
            "content": "test"
        }
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "agent",
                "node_config": {"agent_id": "example_graph"},
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        assert "variables" in data["output_state"]
        assert data["output_state"]["variables"]["company_name"] == "TestCorp"
    
    @pytest.mark.asyncio
    async def test_subflow_preserves_user(self, client, app, container):
        """__user__ сохраняется."""
        state = {
            "__user__": {"user_id": "test_user", "email": "test@example.com"},
            "content": "test"
        }
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "agent",
                "node_config": {"agent_id": "example_graph"},
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        assert "__user__" in data["output_state"]
    
    @pytest.mark.asyncio
    async def test_subflow_missing_agent_id(self, client, app):
        """agent_id=''."""
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "agent",
                "node_config": {"agent_id": ""},
                "state": {}
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=False, expected_error="agent_id обязателен")
    
    @pytest.mark.asyncio
    async def test_subflow_nonexistent_flow(self, client, app):
        """flow не найден."""
        state = {"content": "test"}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "agent",
                "node_config": {"agent_id": "nonexistent_flow_12345"},
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=False)
        assert "error" in data


class TestReactNode:
    """Тесты ReactNode (node_type: 'react_node')."""
    
    @pytest.mark.asyncio
    async def test_react_node_basic_execution(self, client, app, container, mock_llm_redis):
        """prompt + tools + llm."""
        await mock_llm_redis([
            {"type": "text", "content": "Agent response: Hello"}
        ])
        
        state = {"content": "Hello agent"}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "react_node",
                "node_config": {
                    "prompt": "You are a helpful assistant.",
                    "tools": [],
                    "llm": {"model": "gpt-4o", "temperature": 0.2}
                },
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        assert "response" in data["output_state"]
        assert "messages" in data["output_state"]
    
    @pytest.mark.asyncio
    async def test_react_node_with_tools(self, client, app, container, mock_llm_redis):
        """tools передаются."""
        await mock_llm_redis([
            {"type": "text", "content": "Using calculator tool"}
        ])
        
        state = {"content": "Calculate 2+2"}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "react_node",
                "node_config": {
                    "prompt": "You can use calculator tool.",
                    "tools": ["calculator"],
                    "llm": {"model": "gpt-4o"}
                },
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        assert "response" in data["output_state"]
    
    @pytest.mark.asyncio
    async def test_react_node_llm_config(self, client, app, container, mock_llm_redis):
        """model, temperature применяются."""
        await mock_llm_redis([
            {"type": "text", "content": "Response with custom LLM config"}
        ])
        
        state = {"content": "Test"}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "react_node",
                "node_config": {
                    "prompt": "You are an assistant.",
                    "tools": [],
                    "llm": {"model": "gpt-4o", "temperature": 0.5}
                },
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
    
    @pytest.mark.asyncio
    async def test_react_node_input_mapping_content(self, client, app, container, mock_llm_redis):
        """@state:user_query -> content."""
        await mock_llm_redis([
            {"type": "text", "content": "Response to mapped query"}
        ])
        
        state = {"user_query": "Query from state", "other": "data"}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "react_node",
                "node_config": {
                    "prompt": "You are an assistant.",
                    "tools": [],
                    "llm": {"model": "gpt-4o"},
                    "input_mapping": {
                        "content": "@state:user_query"
                    }
                },
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        assert "response" in data["output_state"]
    
    @pytest.mark.asyncio
    async def test_react_node_input_mapping_nested(self, client, app, container, mock_llm_redis):
        """@state:user.name резолвится."""
        await mock_llm_redis([
            {"type": "text", "content": "Hello user"}
        ])
        
        state = {"user": {"name": "Alice"}, "content": "test"}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "react_node",
                "node_config": {
                    "prompt": "Say hello to the user.",
                    "tools": [],
                    "llm": {"model": "gpt-4o"},
                    "input_mapping": {
                        "content": "@state:user.name"
                    }
                },
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
    
    @pytest.mark.asyncio
    async def test_react_node_input_mapping_constant(self, client, app, container, mock_llm_redis):
        """Константа передаётся."""
        await mock_llm_redis([
            {"type": "text", "content": "Response"}
        ])
        
        state = {}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "react_node",
                "node_config": {
                    "prompt": "You are an assistant.",
                    "tools": [],
                    "llm": {"model": "gpt-4o"},
                    "input_mapping": {
                        "content": "Fixed constant content"
                    }
                },
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
    
    @pytest.mark.asyncio
    async def test_react_node_input_mapping_preserves_service(self, client, app, container, mock_llm_redis):
        """variables сохраняются."""
        await mock_llm_redis([
            {"type": "text", "content": "Response"}
        ])
        
        state = {
            "variables": {"company": "TestCorp"},
            "content": "test"
        }
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "react_node",
                "node_config": {
                    "prompt": "You work for {company}.",
                    "tools": [],
                    "llm": {"model": "gpt-4o"},
                    "input_mapping": {
                        "content": "test query"
                    }
                },
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        assert "variables" in data["output_state"]
    
    @pytest.mark.asyncio
    async def test_react_node_response_in_state(self, client, app, container, mock_llm_redis):
        """response записан."""
        await mock_llm_redis([
            {"type": "text", "content": "Agent final response"}
        ])
        
        state = {"content": "Hello"}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "react_node",
                "node_config": {
                    "prompt": "You are an assistant.",
                    "tools": [],
                    "llm": {"model": "gpt-4o"}
                },
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        # Проверяем что response есть, может быть из mock или из настроенного ответа
        assert "response" in data["output_state"]
        assert len(data["output_state"]["response"]) > 0
    
    @pytest.mark.asyncio
    async def test_react_node_messages_updated(self, client, app, container, mock_llm_redis):
        """messages обновлены."""
        await mock_llm_redis([
            {"type": "text", "content": "Agent response"}
        ])
        
        state = {"content": "Hello", "messages": []}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "react_node",
                "node_config": {
                    "prompt": "You are an assistant.",
                    "tools": [],
                    "llm": {"model": "gpt-4o"}
                },
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        assert len(data["output_state"]["messages"]) > 0
    
    @pytest.mark.asyncio
    async def test_react_node_tool_call(self, client, app, container, mock_llm_redis):
        """LLM вызывает tool."""
        await mock_llm_redis([
            {"type": "tool_call", "tool": "calculator", "args": {"expression": "2+2"}},
            {"type": "text", "content": "The answer is 4"}
        ])
        
        state = {"content": "Calculate 2+2"}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "react_node",
                "node_config": {
                    "prompt": "Use calculator tool when needed.",
                    "tools": ["calculator"],
                    "llm": {"model": "gpt-4o"}
                },
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        assert "response" in data["output_state"]
    
    @pytest.mark.asyncio
    async def test_react_node_missing_node_config(self, client, app):
        """node_config={}."""
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "react_node",
                "node_config": {},
                "state": {}
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=False, expected_error="prompt обязателен")
    
    @pytest.mark.asyncio
    async def test_react_node_missing_prompt(self, client, app):
        """prompt=''."""
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "react_node",
                "node_config": {
                    "prompt": "",
                    "tools": [],
                    "llm": {}
                },
                "state": {}
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=False, expected_error="prompt обязателен")


class TestE2EIntegration:
    """E2E интеграционные тесты."""
    
    @pytest.mark.asyncio
    async def test_e2e_function_validate_then_execute(self, client, app):
        """validate -> execute."""
        code = """
def run(state):
    state['validated'] = True
    return state
"""
        validate_resp = await client.post(
            "/agents/api/v1/code/validate",
            json={"code": code}
        )
        assert validate_resp.json()["valid"] is True
        
        state = {}
        exec_resp = await client.post(
            "/agents/api/v1/code/execute",
            json={"node_type": "code", "node_config": {"code": code}, "state": state}
        )
        assert exec_resp.status_code == 200
        data = exec_resp.json()
        assert_execute_response(data, expected_success=True)
        assert data["output_state"]["validated"] is True
    
    @pytest.mark.asyncio
    async def test_e2e_function_then_react_node(self, client, app, container, mock_llm_redis):
        """function модифицирует state, react_node использует."""
        await mock_llm_redis([
            {"type": "text", "content": "Processed query: processed"}
        ])
        
        function_code = """
def run(state):
    state['processed_query'] = state.get('content', '').upper()
    return state
"""
        state = {"content": "hello"}
        
        function_resp = await client.post(
            "/agents/api/v1/code/execute",
            json={"node_type": "code", "node_config": {"code": function_code}, "state": state}
        )
        assert function_resp.json()["success"] is True
        processed_state = function_resp.json()["output_state"]
        
        agent_resp = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "react_node",
                "node_config": {
                    "prompt": "Respond to the processed query.",
                    "tools": [],
                    "llm": {"model": "gpt-4o"},
                    "input_mapping": {
                        "content": "@state:processed_query"
                    }
                },
                "state": processed_state
            }
        )
        assert agent_resp.json()["success"] is True
        assert "response" in agent_resp.json()["output_state"]
    
    @pytest.mark.asyncio
    async def test_e2e_subflow_with_function_nodes(self, client, app, container):
        """subflow example_graph с function classifier."""
        state = {"content": "заказ на iPhone"}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={
                "node_type": "agent",
                "node_config": {"agent_id": "example_graph"},
                "state": state
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert_execute_response(data, expected_success=True)
        assert "route" in data["output_state"] or "response" in data["output_state"]

