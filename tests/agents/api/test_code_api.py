"""
Интеграционные тесты для API /api/v1/code.

Тестируют:
- /code/completions - данные для autocomplete
- /code/validate - валидация inline кода
- /code/execute - выполнение кода с тестовым state
- /code/source - получение исходного кода функции

Все тесты используют реальный API без моков.
"""

import pytest


class TestCodeCompletions:
    """Тесты /api/v1/code/completions"""

    @pytest.mark.asyncio
    async def test_get_completions(self, client, app):
        """Получение данных для autocomplete."""
        response = await client.get("/agents/api/v1/code/completions")
        assert response.status_code == 200
        
        data = response.json()
        
        # Проверяем modules
        assert "modules" in data
        assert "json" in data["modules"]
        assert "re" in data["modules"]
        assert "datetime" in data["modules"]
        
        # Проверяем globals
        assert "globals" in data
        global_names = [g["name"] for g in data["globals"]]
        assert "llm" in global_names
        assert "context" in global_names
        assert "variables" in global_names
        
        # Проверяем builtins
        assert "builtins" in data
        assert "len" in data["builtins"]
        assert "str" in data["builtins"]
        assert "print" in data["builtins"]
        # Заблокированные не должны присутствовать
        assert "eval" not in data["builtins"]
        assert "exec" not in data["builtins"]
        
        # Проверяем module_methods
        assert "module_methods" in data
        assert "json" in data["module_methods"]
        json_methods = [m["name"] for m in data["module_methods"]["json"]]
        assert "loads" in json_methods
        assert "dumps" in json_methods


class TestCodeValidate:
    """Тесты /api/v1/code/validate"""

    @pytest.mark.asyncio
    async def test_validate_valid_sync_code(self, client, app):
        """Валидация корректного синхронного кода."""
        code = """
def run(state):
    state['result'] = 'ok'
    return state
"""
        response = await client.post(
            "/agents/api/v1/code/validate",
            json={"code": code}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["valid"] is True
        assert data["error"] is None

    @pytest.mark.asyncio
    async def test_validate_valid_async_code(self, client, app):
        """Валидация корректного асинхронного кода."""
        code = """
async def run(state):
    state['result'] = 'ok'
    return state
"""
        response = await client.post(
            "/agents/api/v1/code/validate",
            json={"code": code}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["valid"] is True
        assert data["error"] is None
        assert len(data["warnings"]) == 0

    @pytest.mark.asyncio
    async def test_validate_syntax_error(self, client, app):
        """Валидация кода с синтаксической ошибкой."""
        code = """
def run(state)  # missing colon
    return state
"""
        response = await client.post(
            "/agents/api/v1/code/validate",
            json={"code": code}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["valid"] is False
        assert "error" in data
        assert data["error"] is not None

    @pytest.mark.asyncio
    async def test_validate_blocked_import(self, client, app):
        """Валидация кода с запрещённым импортом."""
        code = """
import os

def run(state):
    state['files'] = os.listdir('/')
    return state
"""
        response = await client.post(
            "/agents/api/v1/code/validate",
            json={"code": code}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["valid"] is False
        assert "os" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_validate_allowed_import(self, client, app):
        """Валидация кода с разрешённым импортом."""
        code = """
import json
import re

async def run(state):
    data = json.loads(state.get('json_input', '{}'))
    state['parsed'] = data
    return state
"""
        response = await client.post(
            "/agents/api/v1/code/validate",
            json={"code": code}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["valid"] is True

    @pytest.mark.asyncio
    async def test_validate_any_function_name(self, client, app):
        """Валидация кода с любым именем функции - valid."""
        code = """
def process(state):
    return state
"""
        response = await client.post(
            "/agents/api/v1/code/validate",
            json={"code": code}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["valid"] is True
        assert data["error"] is None

    @pytest.mark.asyncio
    async def test_validate_empty_code(self, client, app):
        """Валидация пустого кода."""
        response = await client.post(
            "/agents/api/v1/code/validate",
            json={"code": ""}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["valid"] is False


class TestCodeExecute:
    """Тесты /api/v1/code/execute"""

    @pytest.mark.asyncio
    async def test_execute_simple_code(self, client, app):
        """Выполнение простого кода."""
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
        assert data["success"] is True, f"Expected success but got error: {data.get('error')}"
        assert data["error"] is None
        assert data["output_state"]["result"] == "executed"
        assert data["output_state"]["doubled"] == 42
        assert data["duration_ms"] >= 0

    @pytest.mark.asyncio
    async def test_execute_with_diff(self, client, app):
        """Выполнение кода с проверкой diff."""
        code = """
def run(state):
    state['new_field'] = 'added'
    state['existing'] = 'modified'
    return state
"""
        state = {"existing": "original", "unchanged": "same"}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={"node_type": "code", "node_config": {"code": code}, "state": state}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
        
        # Проверяем diff
        diff = data["diff"]
        assert len(diff) == 2
        
        # Найдём diff items
        diff_by_path = {d["path"]: d for d in diff}
        
        # new_field - добавлено
        assert "new_field" in diff_by_path
        assert diff_by_path["new_field"]["change_type"] == "added"
        assert diff_by_path["new_field"]["new_value"] == "added"
        
        # existing - изменено
        assert "existing" in diff_by_path
        assert diff_by_path["existing"]["change_type"] == "changed"
        assert diff_by_path["existing"]["old_value"] == "original"
        assert diff_by_path["existing"]["new_value"] == "modified"

    @pytest.mark.asyncio
    async def test_execute_no_changes(self, client, app):
        """Выполнение кода без изменений state."""
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
        assert data["success"] is True
        assert len(data["diff"]) == 0

    @pytest.mark.asyncio
    async def test_execute_with_variables(self, client, app):
        """Выполнение кода с доступом к variables."""
        code = """
def run(state):
    greeting = variables.get('greeting', 'Hello')
    state['message'] = f"{greeting}, World!"
    return state
"""
        state = {
            "variables": {"greeting": "Привет"}
        }
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={"node_type": "code", "node_config": {"code": code}, "state": state}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
        assert data["output_state"]["message"] == "Привет, World!"

    @pytest.mark.asyncio
    async def test_execute_with_json(self, client, app):
        """Выполнение кода с json импортом."""
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
        assert data["success"] is True
        assert data["output_state"]["parsed_name"] == "Test"

    @pytest.mark.asyncio
    async def test_execute_runtime_error(self, client, app):
        """Выполнение кода с runtime ошибкой."""
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
        assert data["success"] is False
        assert "Intentional error" in data["error"]
        assert data["duration_ms"] >= 0

    @pytest.mark.asyncio
    async def test_execute_blocked_import(self, client, app):
        """Выполнение кода с запрещённым импортом."""
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
        assert data["success"] is False
        assert "os" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_execute_async_code(self, client, app):
        """Выполнение асинхронного кода."""
        code = """
async def run(state):
    state['async_result'] = 'async_ok'
    return state
"""
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={"node_type": "code", "node_config": {"code": code}, "state": {}}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
        assert data["output_state"]["async_result"] == "async_ok"

    @pytest.mark.asyncio
    async def test_execute_nested_state_diff(self, client, app):
        """Выполнение с изменением вложенных полей."""
        code = """
def run(state):
    if 'user' not in state:
        state['user'] = {}
    state['user']['name'] = 'Alice'
    state['user']['role'] = 'admin'
    return state
"""
        state = {"user": {"name": "Bob"}}
        
        response = await client.post(
            "/agents/api/v1/code/execute",
            json={"node_type": "code", "node_config": {"code": code}, "state": state}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
        assert data["output_state"]["user"]["name"] == "Alice"
        assert data["output_state"]["user"]["role"] == "admin"
        
        # Проверяем diff
        diff_by_path = {d["path"]: d for d in data["diff"]}
        assert "user.name" in diff_by_path
        assert diff_by_path["user.name"]["change_type"] == "changed"
        assert "user.role" in diff_by_path
        assert diff_by_path["user.role"]["change_type"] == "added"


class TestCodeSource:
    """Тесты /api/v1/code/source"""

    @pytest.mark.asyncio
    async def test_get_source_python_function(self, client, app):
        """Получение исходного кода Python функции."""
        response = await client.get(
            "/agents/api/v1/code/source",
            params={"function_path": "json.loads"}
        )
        assert response.status_code == 200
        
        data = response.json()
        # В Python 3.14+ json.loads - Python функция, source доступен
        # В более ранних версиях - C функция, source недоступен
        # Проверяем что ответ корректный в любом случае
        assert data["path"] == "json.loads"
        assert (data["source"] is not None) or (data["error"] is not None)

    @pytest.mark.asyncio
    async def test_get_source_invalid_path(self, client, app):
        """Получение исходного кода - невалидный путь."""
        response = await client.get(
            "/agents/api/v1/code/source",
            params={"function_path": "invalid"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["source"] is None
        assert data["error"] is not None

    @pytest.mark.asyncio
    async def test_get_source_nonexistent_module(self, client, app):
        """Получение исходного кода - несуществующий модуль."""
        response = await client.get(
            "/agents/api/v1/code/source",
            params={"function_path": "nonexistent_module.some_func"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["source"] is None
        assert "not found" in data["error"].lower()


class TestFlowWithInlineCodeAPI:
    """E2E тесты: создание flow с inline function через API."""

    @pytest.fixture
    async def cleanup_flow(self, container, unique_id):
        """Cleanup fixture для удаления созданных flow."""
        agent_id = f"test_inline_flow_{unique_id}"
        yield agent_id
        # Cleanup после теста
        try:
            await container.agent_repository.delete(agent_id)
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_create_flow_with_inline_function(self, client, app, cleanup_flow, unique_id):
        """Создание flow с inline function нодой через API."""
        agent_id = cleanup_flow
        
        # 1. Создаём flow с inline function
        flow_data = {
            "agent_id": agent_id,
            "name": "Test Inline Agent",
            "description": "Agent for testing inline code",
            "entry": "router",
            "variables": {
                "company": "TestCorp",
                "version": "1.0"
            },
            "nodes": {
                "router": {
                    "type": "code",
                    "code": """
def run(state):
    content = state.get('content', '').lower()
    if 'order' in content:
        state['route'] = 'order'
    elif 'help' in content:
        state['route'] = 'help'
    else:
        state['route'] = 'general'
    return state
"""
                }
            },
            "edges": [
                {"from": "router", "to": None}
            ],
            "tags": ["test", "inline"]
        }
        
        response = await client.post("/agents/api/v1/agents/", json=flow_data)
        assert response.status_code == 200
        
        created = response.json()
        assert created["agent_id"] == agent_id
        assert created["entry"] == "router"

    @pytest.mark.asyncio
    async def test_validate_inline_code_from_flow(self, client, app, cleanup_flow):
        """Валидация inline кода перед созданием flow."""
        # Сначала валидируем код
        code = """
def run(state):
    content = state.get('content', '').lower()
    if 'заказ' in content or 'order' in content:
        state['route'] = 'order'
    elif 'жалоб' in content or 'complaint' in content:
        state['route'] = 'complaint'
    else:
        state['route'] = 'general'
    return state
"""
        
        # Валидация
        response = await client.post(
            "/agents/api/v1/code/validate",
            json={"code": code}
        )
        assert response.status_code == 200
        assert response.json()["valid"] is True

    @pytest.mark.asyncio
    async def test_execute_inline_code_with_flow_variables(self, client, app, cleanup_flow):
        """Тестирование inline кода с переменными flow."""
        code = """
def run(state):
    company = variables.get('company', 'Unknown')
    state['greeting'] = f"Welcome to {company}!"
    state['version'] = variables.get('version', '0.0')
    return state
"""
        
        # Валидация
        validate_response = await client.post(
            "/agents/api/v1/code/validate",
            json={"code": code}
        )
        assert validate_response.json()["valid"] is True
        
        # Выполнение с переменными
        state = {
            "content": "Hello",
            "messages": [],
            "variables": {
                "company": "Platform Corp",
                "version": "2.0"
            }
        }
        
        execute_response = await client.post(
            "/agents/api/v1/code/execute",
            json={"node_type": "code", "node_config": {"code": code}, "state": state}
        )
        assert execute_response.status_code == 200
        
        data = execute_response.json()
        assert data["success"] is True, f"Error: {data.get('error')}"
        assert data["output_state"]["greeting"] == "Welcome to Platform Corp!"
        assert data["output_state"]["version"] == "2.0"
        
        # Проверяем diff
        diff_paths = [d["path"] for d in data["diff"]]
        assert "greeting" in diff_paths
        assert "version" in diff_paths

    @pytest.mark.asyncio
    async def test_full_workflow_validate_execute_create(
        self, client, app, container, cleanup_flow, unique_id
    ):
        """Полный workflow: валидация -> тест -> создание flow."""
        agent_id = cleanup_flow
        
        # 1. Код роутера
        router_code = """
async def run(state):
    content = state.get('content', '').lower()
    
    if 'order' in content or 'заказ' in content:
        state['route'] = 'order'
        state['priority'] = 'high'
    elif 'help' in content or 'помощь' in content:
        state['route'] = 'help'
        state['priority'] = 'medium'
    else:
        state['route'] = 'general'
        state['priority'] = 'low'
    
    return state
"""
        
        # 2. Валидация
        validate_resp = await client.post(
            "/agents/api/v1/code/validate",
            json={"code": router_code}
        )
        assert validate_resp.json()["valid"] is True
        assert len(validate_resp.json()["warnings"]) == 0  # async - нет warnings
        
        # 3. Тест с разными входами
        test_cases = [
            {"content": "I want to order something", "expected_route": "order"},
            {"content": "Нужна помощь", "expected_route": "help"},
            {"content": "Random text", "expected_route": "general"},
        ]
        
        for test in test_cases:
            exec_resp = await client.post(
                "/agents/api/v1/code/execute",
                json={
                    "node_type": "code",
                    "node_config": {"code": router_code},
                    "state": {"content": test["content"], "messages": [], "variables": {}}
                }
            )
            assert exec_resp.json()["success"] is True
            assert exec_resp.json()["output_state"]["route"] == test["expected_route"]
        
        # 4. Создаём flow
        flow_data = {
            "agent_id": agent_id,
            "name": "Router Agent",
            "entry": "router",
            "variables": {"default_priority": "low"},
            "nodes": {
                "router": {
                    "type": "code",
                    "code": router_code
                }
            },
            "edges": [{"from": "router", "to": None}]
        }
        
        create_resp = await client.post("/agents/api/v1/agents/", json=flow_data)
        assert create_resp.status_code == 200
        assert create_resp.json()["agent_id"] == agent_id
        
        # 5. Проверяем что flow создан
        get_resp = await client.get(f"/agents/api/v1/agents/{agent_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["entry"] == "router"

