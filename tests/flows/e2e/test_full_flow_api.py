"""
End-to-End тест: создание и выполнение flow исключительно через API.

Сценарии:
1. Создание flow с variables в промптах через API
2. External API с @var в авторизации
3. Граф с условиями (роутер через edges)
4. Interrupt в функциональной ноде -> resume возвращает к ней
5. Interrupt в tool реакт агента -> resume возвращает к нему
6. Внешний агент с interrupt -> resume возвращает к нему
7. Внешний агент без interrupt -> граф продолжает

Тест работает СНАРУЖИ - только HTTP запросы к API.
Использует фикстуры client и app из conftest.py.
API возвращает A2A Task формат.
"""

from typing import Any, Dict

import pytest
import pytest_asyncio


def get_task_state(data: Dict[str, Any]) -> str:
    """Извлекает state из A2A Task ответа."""
    return data["status"]["state"]


def get_task_response(data: Dict[str, Any]) -> str:
    """Извлекает текст ответа из A2A Task."""
    msg = data["status"].get("message")
    if msg and msg.get("parts"):
        return msg["parts"][0].get("text", "")
    return ""


def _e2e_router_flow_create_payload(flow_id: str) -> dict[str, Any]:
    """Граф классификатора для E2E (условные рёбра)."""
    return {
        "flow_id": flow_id,
        "name": "E2E Router Agent",
        "entry": "classifier",
        "nodes": {
            "classifier": {
                "type": "code",
                "code": "\nasync def run(args, state):\n    content = state.get('content', '')\n    if 'urgent' in content.lower():\n        state['route'] = 'urgent'\n    else:\n        state['route'] = 'normal'\n    return state\n",
            },
            "urgent_handler": {
                "type": "code",
                "code": "async def run(args, state):\n    state['response'] = 'URGENT: Processing immediately!'\n    return state",
            },
            "normal_handler": {
                "type": "code",
                "code": "async def run(args, state):\n    state['response'] = 'Normal: Added to queue'\n    return state",
            },
        },
        "edges": [
            {
                "from_node": "classifier",
                "to_node": "urgent_handler",
                "condition": {
                    "type": "simple",
                    "variable": "route",
                    "operator": "==",
                    "value": "urgent",
                },
            },
            {
                "from_node": "classifier",
                "to_node": "normal_handler",
                "condition": {
                    "type": "simple",
                    "variable": "route",
                    "operator": "==",
                    "value": "normal",
                },
            },
            {"from_node": "urgent_handler", "to_node": None},
            {"from_node": "normal_handler", "to_node": None},
        ],
    }


class TestE2EFlowCreationViaAPI:
    """E2E: Создание flow полностью через API."""

    @pytest.mark.asyncio
    async def test_create_variable_via_api(self, client, auth_headers_system):
        """1. Создаём переменную через API."""
        response = await client.post(
            "/flows/api/v1/variables/",
            json={"key": "e2e_company_name", "value": "E2E Test Company", "secret": False},
            headers=auth_headers_system,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["key"] == "e2e_company_name"

    @pytest.mark.asyncio
    async def test_create_tool_via_api(self, client, auth_headers_system):
        """2. Создаём inline tool через API."""
        response = await client.post(
            "/flows/api/v1/tools/",
            json={
                "tool_id": "e2e_calculator",
                "title": "E2E Calculator",
                "description": "Калькулятор для E2E теста",
                "code": "\nasync def run(args, state):\n    a = args.get('a', 0)\n    b = args.get('b', 0)\n    return a + b\n",
                "parameters_schema": {
                    "type": "object",
                    "properties": {
                        "a": {"type": "number", "description": "First number"},
                        "b": {"type": "number", "description": "Second number"},
                    },
                    "required": ["a", "b"],
                },
            },
            headers=auth_headers_system,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["tool_id"] == "e2e_calculator"

    @pytest.mark.asyncio
    async def test_create_and_execute_simple_flow_via_api(
        self, client, auth_headers_system, unique_id
    ):
        """3+4. Создаём flow (с переменной) и сразу выполняем его через API (один тест, чтобы избежать ordering issues при -n)."""
        var_response = await client.post(
            "/flows/api/v1/variables/",
            json={"key": "e2e_company_name", "value": "E2E Test Company", "secret": False},
            headers=auth_headers_system,
        )
        assert var_response.status_code == 200, f"Failed to create variable: {var_response.text}"
        create_response = await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": "e2e_simple_flow",
                "name": "E2E Simple Agent",
                "description": "Простой flow для E2E теста",
                "entry": "init",
                "nodes": {
                    "init": {
                        "type": "code",
                        "code": "async def run(args, state):\n    return state",
                    },
                    "process": {
                        "type": "code",
                        "code": "async def run(args, state):\n    company = state['variables']['e2e_company_name']\n    state['response'] = f'Hello from {company}!'\n    return state",
                    },
                },
                "edges": [
                    {"from_node": "init", "to_node": "process"},
                    {"from_node": "process", "to_node": None},
                ],
                "variables": {"e2e_company_name": "@var:e2e_company_name"},
            },
            headers=auth_headers_system,
        )
        assert create_response.status_code == 200, (
            f"Failed to create flow: {create_response.status_code}, {create_response.text}"
        )
        create_data = create_response.json()
        assert create_data["flow_id"] == "e2e_simple_flow"
        exec_response = await client.post(
            "/flows/api/v1/tasks/submit",
            json={
                "flow_id": "e2e_simple_flow",
                "session_id": f"e2e_simple_flow:e2e-session-{unique_id}",
                "content": "Hello",
            },
        )
        assert exec_response.status_code == 200
        exec_data = exec_response.json()
        assert get_task_state(exec_data) == "completed"
        assert "E2E Test Company" in get_task_response(exec_data)


class TestE2EFlowWithConditions:
    """E2E: Agent с условиями (роутер через edges)."""

    @pytest.mark.asyncio
    async def test_create_flow_with_router(self, client, auth_headers_system):
        """Создаём flow с условными переходами."""
        response = await client.post(
            "/flows/api/v1/flows/", json=_e2e_router_flow_create_payload("e2e_router_flow")
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_router_flow_urgent_path(self, client, unique_id):
        """Тест urgent пути."""
        flow_id = f"e2e_router_flow_{unique_id}"
        created = await client.post(
            "/flows/api/v1/flows/", json=_e2e_router_flow_create_payload(flow_id)
        )
        assert created.status_code == 200, created.text
        response = await client.post(
            "/flows/api/v1/tasks/submit",
            json={
                "flow_id": flow_id,
                "session_id": f"{flow_id}:e2e-router-urgent-{unique_id}",
                "content": "This is URGENT!",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "URGENT" in get_task_response(data)

    @pytest.mark.asyncio
    async def test_router_flow_normal_path(self, client, unique_id):
        """Тест normal пути."""
        flow_id = f"e2e_router_flow_{unique_id}"
        created = await client.post(
            "/flows/api/v1/flows/", json=_e2e_router_flow_create_payload(flow_id)
        )
        assert created.status_code == 200, created.text
        response = await client.post(
            "/flows/api/v1/tasks/submit",
            json={
                "flow_id": flow_id,
                "session_id": f"{flow_id}:e2e-router-normal-{unique_id}",
                "content": "Regular request",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "Normal" in get_task_response(data)


class TestE2EInterruptInCodeNode:
    """E2E: Interrupt в функциональной ноде."""

    @pytest.mark.asyncio
    async def test_create_flow_with_interrupt_function(self, client, auth_headers_system):
        """Создаём flow где функция делает interrupt."""
        response = await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": "e2e_interrupt_function_flow",
                "name": "E2E Interrupt Function Agent",
                "entry": "ask_name",
                "nodes": {
                    "ask_name": {
                        "type": "code",
                        "code": "\nfrom apps.flows.src.runtime.exceptions import FlowInterrupt\n\nasync def run(args, state):\n    if state.get('user_name'):\n        return state\n    if state.get('asked_name'):\n        state['user_name'] = state.get('content', '')\n        return state\n    state['asked_name'] = True\n    raise FlowInterrupt(question='Как вас зовут?')\n",
                    },
                    "greet": {
                        "type": "code",
                        "code": "\nasync def run(args, state):\n    name = state.get('user_name', 'Guest')\n    state['response'] = f'Привет, {name}!'\n    return state\n",
                    },
                },
                "edges": [
                    {"from_node": "ask_name", "to_node": "greet"},
                    {"from_node": "greet", "to_node": None},
                ],
            },
            headers=auth_headers_system,
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_interrupt_and_resume_function_node(self, client, unique_id, auth_headers_system):
        """Interrupt в функции -> resume -> управление к ней же."""
        create = await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": "e2e_interrupt_function_flow",
                "name": "E2E Interrupt Function Agent",
                "entry": "ask_name",
                "nodes": {
                    "ask_name": {
                        "type": "code",
                        "code": "\nfrom apps.flows.src.runtime.exceptions import FlowInterrupt\n\nasync def run(args, state):\n    if state.get('user_name'):\n        return state\n    if state.get('asked_name'):\n        state['user_name'] = state.get('content', '')\n        return state\n    state['asked_name'] = True\n    raise FlowInterrupt(question='Как вас зовут?')\n",
                    },
                    "greet": {
                        "type": "code",
                        "code": "\nasync def run(args, state):\n    name = state.get('user_name', 'Guest')\n    state['response'] = f'Привет, {name}!'\n    return state\n",
                    },
                },
                "edges": [
                    {"from_node": "ask_name", "to_node": "greet"},
                    {"from_node": "greet", "to_node": None},
                ],
            },
            headers=auth_headers_system,
        )
        assert create.status_code == 200, create.text
        response = await client.post(
            "/flows/api/v1/tasks/submit",
            json={
                "flow_id": "e2e_interrupt_function_flow",
                "session_id": f"e2e_interrupt_function_flow:e2e-interrupt-func-{unique_id}",
                "content": "Начать",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert get_task_state(data) == "input-required"
        assert "Как вас зовут" in get_task_response(data)


class TestE2EInterruptInCodeNodeV2:
    """E2E: Interrupt в функциональной ноде (правильная версия)."""

    @pytest.mark.asyncio
    async def test_interrupt_resume_full_cycle(self, client):
        """
        Полный цикл: создание flow -> interrupt -> resume.
        Проверяем что после resume управление возвращается в ту же ноду.
        """
        import uuid

        flow_id = f"e2e_interrupt_v2_{uuid.uuid4().hex[:8]}"
        context_id = uuid.uuid4().hex[:8]
        session_id = f"{flow_id}:session_{context_id}"
        create_response = await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "E2E Interrupt Function V2",
                "entry": "ask_name",
                "nodes": {
                    "ask_name": {
                        "type": "code",
                        "code": "\nfrom apps.flows.src.runtime.exceptions import FlowInterrupt\n\nasync def run(args, state):\n    # Не используем ключ user_name: в state['variables'] уже есть user_name из JWT\n    # (flow_variables_from_request_context), иначе interrupt никогда не сработает.\n    variables = state['variables']\n    if 'interrupt_demo_name' in variables:\n        return state\n\n    content = state['content']\n    if content != 'Start':\n        variables['interrupt_demo_name'] = content\n        return state\n\n    raise FlowInterrupt(question='Как вас зовут?')\n",
                    },
                    "greet": {
                        "type": "code",
                        "code": "\nasync def run(args, state):\n    name = state['variables']['interrupt_demo_name']\n    state['response'] = f'Привет, {name}!'\n    return state\n",
                    },
                },
                "edges": [
                    {"from_node": "ask_name", "to_node": "greet"},
                    {"from_node": "greet", "to_node": None},
                ],
                "variables": {},
            },
        )
        assert create_response.status_code == 200
        r1 = await client.post(
            "/flows/api/v1/tasks/submit",
            json={"flow_id": flow_id, "session_id": session_id, "content": "Start"},
        )
        assert r1.status_code == 200
        d1 = r1.json()
        assert get_task_state(d1) == "input-required", f"Expected input-required, got: {d1}"
        assert "Как вас зовут" in get_task_response(d1)
        r2 = await client.post(
            "/flows/api/v1/tasks/submit",
            json={"flow_id": flow_id, "session_id": session_id, "content": "Иван"},
        )
        assert r2.status_code == 200
        d2 = r2.json()
        assert get_task_state(d2) == "completed", f"Expected completed, got: {d2}"
        assert "Привет, Иван" in get_task_response(d2)


class TestE2EExternalAPIWithVarAuth:
    """E2E: External API с @var в авторизации."""

    @pytest.mark.asyncio
    async def test_create_var_for_auth(self, client, auth_headers_system):
        """Создаём переменную для токена авторизации."""
        response = await client.post(
            "/flows/api/v1/variables/",
            json={"key": "e2e_api_token", "value": "Bearer secret-e2e-token", "secret": True},
            headers=auth_headers_system,
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_create_flow_with_external_api_var_auth(self, client, auth_headers_system):
        """Agent с external_api нодой где @var в headers."""
        response = await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": "e2e_external_api_var_flow",
                "name": "E2E External API with @var",
                "entry": "call_api",
                "nodes": {
                    "call_api": {
                        "type": "external_api",
                        "url": "http://example.com/api/data",
                        "method": "GET",
                        "headers": {"Authorization": "@var:e2e_api_token"},
                        "state_mapping": {"api_result": "response.data"},
                    },
                    "format_result": {
                        "type": "code",
                        "code": "\nasync def run(args, state):\n    result = state.get('api_result', 'No data')\n    state['response'] = f'API returned: {result}'\n    return state\n",
                    },
                },
                "edges": [
                    {"from_node": "call_api", "to_node": "format_result"},
                    {"from_node": "format_result", "to_node": None},
                ],
                "variables": {"e2e_api_token": "test-api-key"},
            },
        )
        assert response.status_code == 200


class TestE2EMultipleInterruptScenarios:
    """E2E: Несколько сценариев с interrupt."""

    @pytest_asyncio.fixture(autouse=True)
    async def setup_complex_flow(self, client, auth_headers_system):
        """Создаёт flow перед каждым тестом."""
        response = await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": "e2e_complex_interrupt_flow",
                "name": "E2E Complex Agent",
                "entry": "classifier",
                "nodes": {
                    "classifier": {
                        "type": "code",
                        "code": "\nasync def run(args, state):\n    content = state.get('content', '').lower()\n    if 'order' in content:\n        state['route'] = 'order'\n    elif 'support' in content:\n        state['route'] = 'support'\n    else:\n        state['route'] = 'general'\n    return state\n",
                    },
                    "order_handler": {
                        "type": "code",
                        "code": "\nfrom apps.flows.src.runtime.exceptions import FlowInterrupt\n\nasync def run(args, state):\n    if 'order_id' in state:\n        state['response'] = f\"Заказ {state['order_id']} найден!\"\n        return state\n    if state.get('was_interrupted_order'):\n        state['order_id'] = state.get('content', '')\n        state['response'] = f\"Заказ {state['order_id']} найден!\"\n        return state\n    state['was_interrupted_order'] = True\n    raise FlowInterrupt(question='Введите номер заказа:')\n",
                    },
                    "support_handler": {
                        "type": "code",
                        "code": "\nfrom apps.flows.src.runtime.exceptions import FlowInterrupt\n\nasync def run(args, state):\n    if 'problem' in state:\n        state['response'] = f\"Создан тикет по проблеме: {state['problem']}\"\n        return state\n    if state.get('was_interrupted_support'):\n        state['problem'] = state.get('content', '')\n        state['response'] = f\"Создан тикет по проблеме: {state['problem']}\"\n        return state\n    state['was_interrupted_support'] = True\n    raise FlowInterrupt(question='Опишите вашу проблему:')\n",
                    },
                    "general_handler": {
                        "type": "code",
                        "code": "\nasync def run(args, state):\n    state['response'] = 'Добро пожаловать! Напишите \"order\" или \"support\".'\n    return state\n",
                    },
                },
                "edges": [
                    {
                        "from_node": "classifier",
                        "to_node": "order_handler",
                        "condition": {
                            "type": "simple",
                            "variable": "route",
                            "operator": "==",
                            "value": "order",
                        },
                    },
                    {
                        "from_node": "classifier",
                        "to_node": "support_handler",
                        "condition": {
                            "type": "simple",
                            "variable": "route",
                            "operator": "==",
                            "value": "support",
                        },
                    },
                    {
                        "from_node": "classifier",
                        "to_node": "general_handler",
                        "condition": {
                            "type": "simple",
                            "variable": "route",
                            "operator": "==",
                            "value": "general",
                        },
                    },
                    {"from_node": "order_handler", "to_node": None},
                    {"from_node": "support_handler", "to_node": None},
                    {"from_node": "general_handler", "to_node": None},
                ],
            },
            headers=auth_headers_system,
        )
        assert response.status_code in (200, 409)

    @pytest.mark.asyncio
    async def test_create_complex_flow(self, client, auth_headers_system):
        """Проверяем что flow создан."""
        response = await client.get(
            "/flows/api/v1/e2e_complex_interrupt_flow", headers=auth_headers_system
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_create_complex_flow_original(self, client, auth_headers_system):
        """Создаём сложный flow с несколькими interrupt точками."""
        response = await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": "e2e_complex_interrupt_flow",
                "name": "E2E Complex Agent",
                "entry": "classifier",
                "nodes": {
                    "classifier": {
                        "type": "code",
                        "code": "\nasync def run(args, state):\n    content = state.get('content', '').lower()\n    if 'order' in content:\n        state['route'] = 'order'\n    elif 'support' in content:\n        state['route'] = 'support'\n    else:\n        state['route'] = 'general'\n    return state\n",
                    },
                    "order_handler": {
                        "type": "code",
                        "code": "\nfrom apps.flows.src.runtime.exceptions import FlowInterrupt\n\nasync def run(args, state):\n    if 'order_id' in state:\n        state['response'] = f\"Заказ {state['order_id']} найден!\"\n        return state\n    if state.get('was_interrupted_order'):\n        state['order_id'] = state.get('content', '')\n        state['response'] = f\"Заказ {state['order_id']} найден!\"\n        return state\n    state['was_interrupted_order'] = True\n    raise FlowInterrupt(question='Введите номер заказа:')\n",
                    },
                    "support_handler": {
                        "type": "code",
                        "code": "\nfrom apps.flows.src.runtime.exceptions import FlowInterrupt\n\nasync def run(args, state):\n    if 'problem' in state:\n        state['response'] = f\"Создан тикет по проблеме: {state['problem']}\"\n        return state\n    if state.get('was_interrupted_support'):\n        state['problem'] = state.get('content', '')\n        state['response'] = f\"Создан тикет по проблеме: {state['problem']}\"\n        return state\n    state['was_interrupted_support'] = True\n    raise FlowInterrupt(question='Опишите вашу проблему:')\n",
                    },
                    "general_handler": {
                        "type": "code",
                        "code": "\nasync def run(args, state):\n    state['response'] = 'Добро пожаловать! Напишите \"order\" или \"support\".'\n    return state\n",
                    },
                },
                "edges": [
                    {
                        "from_node": "classifier",
                        "to_node": "order_handler",
                        "condition": {
                            "type": "simple",
                            "variable": "route",
                            "operator": "==",
                            "value": "order",
                        },
                    },
                    {
                        "from_node": "classifier",
                        "to_node": "support_handler",
                        "condition": {
                            "type": "simple",
                            "variable": "route",
                            "operator": "==",
                            "value": "support",
                        },
                    },
                    {
                        "from_node": "classifier",
                        "to_node": "general_handler",
                        "condition": {
                            "type": "simple",
                            "variable": "route",
                            "operator": "==",
                            "value": "general",
                        },
                    },
                    {"from_node": "order_handler", "to_node": None},
                    {"from_node": "support_handler", "to_node": None},
                    {"from_node": "general_handler", "to_node": None},
                ],
            },
            headers=auth_headers_system,
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_order_path_with_interrupt(self, client, unique_id):
        """Order путь с interrupt."""
        session_id = f"e2e_complex_interrupt_flow:e2e-complex-order-{unique_id}"
        r1 = await client.post(
            "/flows/api/v1/tasks/submit",
            json={
                "flow_id": "e2e_complex_interrupt_flow",
                "session_id": session_id,
                "content": "Check my order",
            },
        )
        assert r1.status_code == 200
        d1 = r1.json()
        assert get_task_state(d1) == "input-required"
        assert "номер заказа" in get_task_response(d1)
        r2 = await client.post(
            "/flows/api/v1/tasks/submit",
            json={
                "flow_id": "e2e_complex_interrupt_flow",
                "session_id": session_id,
                "content": "ORD-12345",
            },
        )
        assert r2.status_code == 200
        d2 = r2.json()
        assert get_task_state(d2) == "completed"
        assert "ORD-12345" in get_task_response(d2)

    @pytest.mark.asyncio
    async def test_support_path_with_interrupt(self, client, unique_id):
        """Support путь с interrupt."""
        session_id = f"e2e_complex_interrupt_flow:e2e-complex-support-{unique_id}"
        r1 = await client.post(
            "/flows/api/v1/tasks/submit",
            json={
                "flow_id": "e2e_complex_interrupt_flow",
                "session_id": session_id,
                "content": "I need support",
            },
        )
        assert r1.status_code == 200
        d1 = r1.json()
        assert get_task_state(d1) == "input-required"
        assert "проблему" in get_task_response(d1)
        r2 = await client.post(
            "/flows/api/v1/tasks/submit",
            json={
                "flow_id": "e2e_complex_interrupt_flow",
                "session_id": session_id,
                "content": "Не работает кнопка",
            },
        )
        assert r2.status_code == 200
        d2 = r2.json()
        assert get_task_state(d2) == "completed"
        assert "Не работает кнопка" in get_task_response(d2)

    @pytest.mark.asyncio
    async def test_general_path_no_interrupt(self, client, unique_id):
        """General путь без interrupt."""
        response = await client.post(
            "/flows/api/v1/tasks/submit",
            json={
                "flow_id": "e2e_complex_interrupt_flow",
                "session_id": f"e2e_complex_interrupt_flow:e2e-complex-general-{unique_id}",
                "content": "Hello",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert get_task_state(data) == "completed"
        assert "Добро пожаловать" in get_task_response(data)


class TestE2EExternalA2AInFlow:
    """E2E: внешний A2A endpoint внутри flow."""

    @pytest.mark.asyncio
    async def test_create_flow_with_remote_flow_node(self, client, auth_headers_system):
        """Создание flow с нодой remote_flow через API."""
        response = await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": "e2e_remote_a2a_flow",
                "name": "E2E Remote A2A",
                "entry": "call_remote",
                "nodes": {
                    "call_remote": {
                        "type": "remote_flow",
                        "url": "http://external-agent:8080",
                        "branch_id": "default",
                    },
                    "process_result": {
                        "type": "code",
                        "code": "\nasync def run(args, state):\n    agent_response = state.get('response', '')\n    state['response'] = f'Agent said: {agent_response}'\n    return state\n",
                    },
                },
                "edges": [
                    {"from_node": "call_remote", "to_node": "process_result"},
                    {"from_node": "process_result", "to_node": None},
                ],
            },
            headers=auth_headers_system,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["flow_id"] == "e2e_remote_a2a_flow"


class TestE2EFullScenario:
    """E2E: Полный сценарий с созданием всего через API."""

    @pytest.mark.asyncio
    async def test_full_e2e_scenario(self, client, unique_id, auth_headers_system):
        """
        Полный E2E сценарий:
        1. Создаём переменные
        2. Создаём tools
        3. Создаём flow
        4. Выполняем с interrupt/resume
        """
        await client.post(
            "/flows/api/v1/variables/",
            json={
                "key": "e2e_full_greeting",
                "value": "Добро пожаловать в E2E тест!",
                "secret": False,
            },
            headers=auth_headers_system,
        )
        await client.post(
            "/flows/api/v1/tools/",
            json={
                "tool_id": "e2e_full_formatter",
                "title": "E2E Formatter",
                "description": "Форматирует текст",
                "code": "\nasync def run(args, state):\n    text = args.get('text', '')\n    return f'[FORMATTED] {text}'\n",
                "parameters_schema": {
                    "type": "object",
                    "properties": {"text": {"type": "string", "description": "Text to format"}},
                    "required": ["text"],
                },
            },
            headers=auth_headers_system,
        )
        create_resp = await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": "e2e_full_scenario_flow",
                "name": "E2E Full Scenario",
                "entry": "welcome",
                "nodes": {
                    "welcome": {
                        "type": "code",
                        "code": "\nasync def run(args, state):\n    greeting = state.get('variables', {}).get('greeting', 'Hello')\n    state['welcome_msg'] = greeting\n    return state\n",
                    },
                    "ask_action": {
                        "type": "code",
                        "code": "\nfrom apps.flows.src.runtime.exceptions import FlowInterrupt\n\nasync def run(args, state):\n    if 'action' in state:\n        return state\n    if state.get('asked_action'):\n        state['action'] = state.get('content', '').lower()\n        return state\n    state['asked_action'] = True\n    raise FlowInterrupt(question=state['welcome_msg'] + ' Что вы хотите сделать?')\n",
                    },
                    "process_action": {
                        "type": "code",
                        "code": "\nasync def run(args, state):\n    action = state.get('action', '')\n    if 'calc' in action:\n        state['response'] = 'Калькулятор: 2+2=4'\n    elif 'help' in action:\n        state['response'] = 'Помощь: напишите calc или help'\n    else:\n        state['response'] = f'Неизвестное действие: {action}'\n    return state\n",
                    },
                },
                "edges": [
                    {"from_node": "welcome", "to_node": "ask_action"},
                    {"from_node": "ask_action", "to_node": "process_action"},
                    {"from_node": "process_action", "to_node": None},
                ],
                "variables": {
                    "greeting": "@var:e2e_full_greeting",
                    "e2e_full_greeting": "Добро пожаловать в E2E тест!",
                },
            },
            headers=auth_headers_system,
        )
        assert create_resp.status_code == 200, f"Failed to create agent: {create_resp.text}"
        session_id = f"e2e_full_scenario_flow:e2e-full-{unique_id}"
        r1 = await client.post(
            "/flows/api/v1/tasks/submit",
            json={
                "flow_id": "e2e_full_scenario_flow",
                "session_id": session_id,
                "content": "Start",
            },
        )
        assert r1.status_code == 200
        d1 = r1.json()
        assert get_task_state(d1) == "input-required"
        assert "E2E тест" in get_task_response(d1)
        assert "Что вы хотите" in get_task_response(d1)
        r2 = await client.post(
            "/flows/api/v1/tasks/submit",
            json={"flow_id": "e2e_full_scenario_flow", "session_id": session_id, "content": "calc"},
        )
        assert r2.status_code == 200
        d2 = r2.json()
        assert get_task_state(d2) == "completed"
        assert "2+2=4" in get_task_response(d2)
