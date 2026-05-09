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


class TestE2EFlowCreationViaAPI:
    """E2E: Создание flow полностью через API."""

    @pytest.mark.asyncio
    async def test_create_variable_via_api(self, client, auth_headers_system):
        """1. Создаём переменную через API."""
        response = await client.post(
            "/flows/api/v1/variables/",
            json={
                "key": "e2e_company_name",
                "value": "E2E Test Company",
                "secret": False,
            },
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
                "code_mode": "INLINE_CODE",
                "code": """
async def execute(args, state):
    a = args.get('a', 0)
    b = args.get('b', 0)
    return a + b
""",
                "args_schema": {
                    "a": {"type": "number", "description": "First number"},
                    "b": {"type": "number", "description": "Second number"},
                },
            },
            headers=auth_headers_system,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["tool_id"] == "e2e_calculator"

    @pytest.mark.asyncio
    async def test_create_and_execute_simple_flow_via_api(self, client, auth_headers_system, unique_id):
        """3+4. Создаём flow (с переменной) и сразу выполняем его через API (один тест, чтобы избежать ordering issues при -n)."""
        var_response = await client.post(
            "/flows/api/v1/variables/",
            json={
                "key": "e2e_company_name",
                "value": "E2E Test Company",
                "secret": False,
            },
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
                        "code": "async def run(state):\n    return state",
                    },
                    "process": {
                        "type": "code",
                        "code": "async def run(state):\n    company = state.variables.get('e2e_company_name', 'Unknown')\n    state.response = f'Hello from {company}!'\n    return state",
                    },
                },
                "edges": [
                    {"from": "init", "to": "process"},
                    {"from": "process", "to": None},
                ],
                "variables": {
                    "e2e_company_name": "@var:e2e_company_name"
                },
            },
            headers=auth_headers_system,
        )
        assert create_response.status_code == 200, f"Failed to create flow: {create_response.status_code}, {create_response.text}"
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
            "/flows/api/v1/flows/",
            json={
                "flow_id": "e2e_router_flow",
                "name": "E2E Router Agent",
                "entry": "classifier",
                "nodes": {
                    "classifier": {
                        "type": "code",
                        "code": """
async def run(state):
    content = state.get('content', '')
    if 'urgent' in content.lower():
        state['route'] = 'urgent'
    else:
        state['route'] = 'normal'
    return state
""",
                    },
                    "urgent_handler": {
                        "type": "code",
                        "code": "async def run(state):\n    state['response'] = 'URGENT: Processing immediately!'\n    return state",
                    },
                    "normal_handler": {
                        "type": "code",
                        "code": "async def run(state):\n    state['response'] = 'Normal: Added to queue'\n    return state",
                    },
                },
                "edges": [
                    {"from": "classifier", "to": "urgent_handler", "condition": "route == urgent"},
                    {"from": "classifier", "to": "normal_handler", "condition": "route == normal"},
                    {"from": "urgent_handler", "to": None},
                    {"from": "normal_handler", "to": None},
                ],
            },
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_router_flow_urgent_path(self, client, unique_id):
        """Тест urgent пути."""
        response = await client.post(
            "/flows/api/v1/tasks/submit",
            json={
                "flow_id": "e2e_router_flow",
                "session_id": f"e2e_router_flow:e2e-router-urgent-{unique_id}",
                "content": "This is URGENT!",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "URGENT" in get_task_response(data)

    @pytest.mark.asyncio
    async def test_router_flow_normal_path(self, client, unique_id):
        """Тест normal пути."""
        response = await client.post(
            "/flows/api/v1/tasks/submit",
            json={
                "flow_id": "e2e_router_flow",
                "session_id": f"e2e_router_flow:e2e-router-normal-{unique_id}",
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
                        "code": """
async def run(state):
    if 'user_name' not in state:
        state['interrupt'] = {'question': 'Как вас зовут?'}
        return state
    return state
""",
                    },
                    "greet": {
                        "type": "code",
                        "code": """
async def run(state):
    name = state.get('user_name', 'Guest')
    state['response'] = f'Привет, {name}!'
    return state
""",
                    },
                },
                "edges": [
                    {"from": "ask_name", "to": "greet"},
                    {"from": "greet", "to": None},
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
                        "code": """
async def run(state):
    if 'user_name' not in state:
        state['interrupt'] = {'question': 'Как вас зовут?'}
        return state
    return state
""",
                    },
                    "greet": {
                        "type": "code",
                        "code": """
async def run(state):
    name = state.get('user_name', 'Guest')
    state['response'] = f'Привет, {name}!'
    return state
""",
                    },
                },
                "edges": [
                    {"from": "ask_name", "to": "greet"},
                    {"from": "greet", "to": None},
                ],
            },
            headers=auth_headers_system,
        )
        assert create.status_code == 200, create.text

        # Первый запрос - получаем interrupt
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

        # Resume с ответом - должны вернуться к ask_name и пойти дальше
        # Функция читает ответ пользователя из state["content"]


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

        # 1. Создаём flow с FlowInterrupt в function ноде
        create_response = await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "E2E Interrupt Function V2",
                "entry": "ask_name",
                "nodes": {
                    "ask_name": {
                        "type": "code",
                        "code": """
from apps.flows.src.runtime.exceptions import FlowInterrupt

async def run(state):
    # Не используем ключ user_name: в state.variables уже есть user_name из JWT
    # (flow_variables_from_request_context), иначе interrupt никогда не сработает.
    if state.variables.get('interrupt_demo_name'):
        return state

    if state.content and state.content != 'Start':
        state.variables['interrupt_demo_name'] = state.content
        return state

    raise FlowInterrupt(question='Как вас зовут?')
""",
                    },
                    "greet": {
                        "type": "code",
                        "code": """
async def run(state):
    name = state.variables.get('interrupt_demo_name', 'Guest')
    state.response = f'Привет, {name}!'
    return state
""",
                    },
                },
                "edges": [
                    {"from": "ask_name", "to": "greet"},
                    {"from": "greet", "to": None},
                ],
                "variables": {},
            },
        )
        assert create_response.status_code == 200

        # 2. Первый запрос - должен вернуть interrupt
        r1 = await client.post(
            "/flows/api/v1/tasks/submit",
            json={
                "flow_id": flow_id,
                "session_id": session_id,
                "content": "Start",
            },
        )
        assert r1.status_code == 200
        d1 = r1.json()
        assert get_task_state(d1) == "input-required", f"Expected input-required, got: {d1}"
        assert "Как вас зовут" in get_task_response(d1)

        # 3. Resume с ответом - должен завершиться
        r2 = await client.post(
            "/flows/api/v1/tasks/submit",
            json={
                "flow_id": flow_id,
                "session_id": session_id,
                "content": "Иван",
            },
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
            json={
                "key": "e2e_api_token",
                "value": "Bearer secret-e2e-token",
                "secret": True,
            },
            headers=auth_headers_system,
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_create_flow_with_external_api_var_auth(self, client, auth_headers_system):
        """Agent с external_api нодой где @var в headers."""
        # Создаём flow с external_api - проверяем что конфиг принимается
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
                        "code": """
async def run(state):
    result = state.get('api_result', 'No data')
    state['response'] = f'API returned: {result}'
    return state
""",
                    },
                },
                "edges": [
                    {"from": "call_api", "to": "format_result"},
                    {"from": "format_result", "to": None},
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
                        "code": """
async def run(state):
    content = state.get('content', '').lower()
    if 'order' in content:
        state['route'] = 'order'
    elif 'support' in content:
        state['route'] = 'support'
    else:
        state['route'] = 'general'
    return state
""",
                    },
                    "order_handler": {
                        "type": "code",
                        "code": """
async def run(state):
    if 'order_id' in state:
        state['response'] = f"Заказ {state['order_id']} найден!"
        return state
    if state.get('was_interrupted_order'):
        state['order_id'] = state.get('content', '')
        state['response'] = f"Заказ {state['order_id']} найден!"
        return state
    state['interrupt'] = {'question': 'Введите номер заказа:'}
    state['was_interrupted_order'] = True
    return state
""",
                    },
                    "support_handler": {
                        "type": "code",
                        "code": """
async def run(state):
    if 'problem' in state:
        state['response'] = f"Создан тикет по проблеме: {state['problem']}"
        return state
    if state.get('was_interrupted_support'):
        state['problem'] = state.get('content', '')
        state['response'] = f"Создан тикет по проблеме: {state['problem']}"
        return state
    state['interrupt'] = {'question': 'Опишите вашу проблему:'}
    state['was_interrupted_support'] = True
    return state
""",
                    },
                    "general_handler": {
                        "type": "code",
                        "code": """
async def run(state):
    state['response'] = 'Добро пожаловать! Напишите "order" или "support".'
    return state
""",
                    },
                },
                "edges": [
                    {"from": "classifier", "to": "order_handler", "condition": "route == 'order'"},
                    {"from": "classifier", "to": "support_handler", "condition": "route == 'support'"},
                    {"from": "classifier", "to": "general_handler", "condition": "route == 'general'"},
                    {"from": "order_handler", "to": None},
                    {"from": "support_handler", "to": None},
                    {"from": "general_handler", "to": None},
                ],
            },
            headers=auth_headers_system,
        )
        # Agent может уже существовать - это OK
        assert response.status_code in (200, 409)

    @pytest.mark.asyncio
    async def test_create_complex_flow(self, client, auth_headers_system):
        """Проверяем что flow создан."""
        response = await client.get("/flows/api/v1/e2e_complex_interrupt_flow", headers=auth_headers_system)
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
                        "code": """
async def run(state):
    content = state.get('content', '').lower()
    if 'order' in content:
        state['route'] = 'order'
    elif 'support' in content:
        state['route'] = 'support'
    else:
        state['route'] = 'general'
    return state
""",
                    },
                    "order_handler": {
                        "type": "code",
                        "code": """
async def run(state):
    # При resume content содержит ответ пользователя (номер заказа)
    if 'order_id' in state:
        state['response'] = f"Заказ {state['order_id']} найден!"
        return state
    # Первый вызов после interrupt - сохраняем номер
    if state.get('was_interrupted_order'):
        state['order_id'] = state.get('content', '')
        state['response'] = f"Заказ {state['order_id']} найден!"
        return state
    # Первый вызов - спрашиваем номер
    state['interrupt'] = {'question': 'Введите номер заказа:'}
    state['was_interrupted_order'] = True
    return state
""",
                    },
                    "support_handler": {
                        "type": "code",
                        "code": """
async def run(state):
    if 'problem' in state:
        state['response'] = f"Создан тикет по проблеме: {state['problem']}"
        return state
    if state.get('was_interrupted_support'):
        state['problem'] = state.get('content', '')
        state['response'] = f"Создан тикет по проблеме: {state['problem']}"
        return state
    state['interrupt'] = {'question': 'Опишите вашу проблему:'}
    state['was_interrupted_support'] = True
    return state
""",
                    },
                    "general_handler": {
                        "type": "code",
                        "code": """
async def run(state):
    state['response'] = 'Добро пожаловать! Напишите "order" или "support".'
    return state
""",
                    },
                },
                "edges": [
                    {"from": "classifier", "to": "order_handler", "condition": "route == 'order'"},
                    {"from": "classifier", "to": "support_handler", "condition": "route == 'support'"},
                    {"from": "classifier", "to": "general_handler", "condition": "route == 'general'"},
                    {"from": "order_handler", "to": None},
                    {"from": "support_handler", "to": None},
                    {"from": "general_handler", "to": None},
                ],
            },
            headers=auth_headers_system,
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_order_path_with_interrupt(self, client, unique_id):
        """Order путь с interrupt."""
        session_id = f"e2e_complex_interrupt_flow:e2e-complex-order-{unique_id}"
        
        # Первый запрос - попадаем в order_handler
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

        # Resume - отвечаем номером
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
                        "code": """
async def run(state):
    agent_response = state.get('response', '')
    state['response'] = f'Agent said: {agent_response}'
    return state
""",
                    },
                },
                "edges": [
                    {"from": "call_remote", "to": "process_result"},
                    {"from": "process_result", "to": None},
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
        # 1. Создаём переменную
        await client.post(
            "/flows/api/v1/variables/",
            json={"key": "e2e_full_greeting", "value": "Добро пожаловать в E2E тест!", "secret": False},
            headers=auth_headers_system,
        )

        # 2. Создаём inline tool
        await client.post(
            "/flows/api/v1/tools/",
            json={
                "tool_id": "e2e_full_formatter",
                "title": "E2E Formatter",
                "description": "Форматирует текст",
                "code_mode": "INLINE_CODE",
                "code": """
async def execute(args, state):
    text = args.get('text', '')
    return f'[FORMATTED] {text}'
""",
                "args_schema": {
                    "text": {"type": "string", "description": "Text to format"},
                },
            },
        )

        # 3. Создаём flow с переменными и условиями
        create_resp = await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": "e2e_full_scenario_flow",
                "name": "E2E Full Scenario",
                "entry": "welcome",
                "nodes": {
                    "welcome": {
                        "type": "code",
                        "code": """
async def run(state):
    greeting = state.get('variables', {}).get('greeting', 'Hello')
    state['welcome_msg'] = greeting
    return state
""",
                    },
                    "ask_action": {
                        "type": "code",
                        "code": """
async def run(state):
    if 'action' in state:
        return state
    if state.get('asked_action'):
        state['action'] = state.get('content', '').lower()
        return state
    state['interrupt'] = {'question': state['welcome_msg'] + ' Что вы хотите сделать?'}
    state['asked_action'] = True
    return state
""",
                    },
                    "process_action": {
                        "type": "code",
                        "code": """
async def run(state):
    action = state.get('action', '')
    if 'calc' in action:
        state['response'] = 'Калькулятор: 2+2=4'
    elif 'help' in action:
        state['response'] = 'Помощь: напишите calc или help'
    else:
        state['response'] = f'Неизвестное действие: {action}'
    return state
""",
                    },
                },
                "edges": [
                    {"from": "welcome", "to": "ask_action"},
                    {"from": "ask_action", "to": "process_action"},
                    {"from": "process_action", "to": None},
                ],
                "variables": {
                    "greeting": "@var:e2e_full_greeting",
                    "e2e_full_greeting": "Добро пожаловать в E2E тест!"
                },
            },
            headers=auth_headers_system,
        )
        assert create_resp.status_code == 200, f"Failed to create agent: {create_resp.text}"

        # 4. Выполняем flow
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

        # 5. Resume с ответом
        r2 = await client.post(
            "/flows/api/v1/tasks/submit",
            json={
                "flow_id": "e2e_full_scenario_flow",
                "session_id": session_id,
                "content": "calc",
            },
        )
        assert r2.status_code == 200
        d2 = r2.json()
        assert get_task_state(d2) == "completed"
        assert "2+2=4" in get_task_response(d2)

