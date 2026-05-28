"""
End-to-End тесты для CodeNode.

Сценарии:
1. Создание flow с CodeNode через API и выполнение через A2A
2. CodeNode с input_mapping (@state:, @var:, константы)
3. Цепочка CodeNode в flow
4. CodeNode с вложенными путями в state
5. Условный переход к CodeNode
"""

import uuid
from typing import Any, Dict

import pytest


def _msg(text: str, context_id: str | None = None) -> Dict[str, Any]:
    """Создаёт A2A Message."""
    m = {"messageId": str(uuid.uuid4()), "role": "user", "parts": [{"kind": "text", "text": text}]}
    if context_id:
        m["contextId"] = context_id
    return m


def get_task_from_response(data: Dict[str, Any]) -> Dict[str, Any]:
    """Извлекает Task из JSON-RPC response."""
    return data.get("result", {})


def get_task_state(task: Dict[str, Any]) -> str:
    """Извлекает state из Task."""
    return task.get("status", {}).get("state", "")


def get_task_response(task: Dict[str, Any]) -> str:
    """Извлекает текст ответа из Task."""
    msg = task.get("status", {}).get("message")
    if msg and msg.get("parts"):
        return msg["parts"][0].get("text", "")
    artifacts = task.get("artifacts", [])
    for artifact in reversed(artifacts):
        parts = artifact.get("parts", [])
        for part in parts:
            data = part.get("data", {})
            if data.get("event") == "node_complete" and data.get("result_preview"):
                return data["result_preview"]
    return ""


class TestCodeNodeE2E:
    """E2E тесты CodeNode через A2A API."""

    @pytest.mark.asyncio
    async def test_create_and_execute_inline_tool_node_flow(self, client, unique_id):
        """E2E: Создание flow с inline CodeNode и выполнение через A2A."""
        flow_id = f"e2e_tool_node_{unique_id}"
        create_response = await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "E2E Tool Node Agent",
                "entry": "prepare",
                "nodes": {
                    "prepare": {
                        "type": "code",
                        "code": "async def run(args, state):\n    state['num1'] = 25\n    state['num2'] = 17\n    return state",
                    },
                    "calculate": {
                        "type": "code",
                        "code": "async def run(args, state):\n    return {'sum': args['a'] + args['b']}",
                        "input_mapping": {"a": "@state:num1", "b": "@state:num2"},
                    },
                    "finish": {
                        "type": "code",
                        "code": "async def run(args, state):\n    state['response'] = f\"Сумма: {state['sum']}\"\n    return state",
                    },
                },
                "edges": [
                    {"from_node": "prepare", "to_node": "calculate"},
                    {"from_node": "calculate", "to_node": "finish"},
                    {"from_node": "finish", "to_node": None},
                ],
            },
        )
        assert create_response.status_code == 200
        exec_response = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": f"test-{unique_id}",
                "method": "message/send",
                "params": {"message": _msg("calculate")},
            },
        )
        assert exec_response.status_code == 200
        data = exec_response.json()
        task = get_task_from_response(data)
        assert get_task_state(task) == "completed"
        response_text = get_task_response(task)
        assert "42" in response_text or "Сумма" in response_text
        await client.delete(f"/flows/api/v1/{flow_id}")

    @pytest.mark.asyncio
    async def test_tool_node_with_variables(self, client, unique_id):
        """E2E: CodeNode использует переменные из flow через A2A."""
        flow_id = f"e2e_tool_var_{unique_id}"
        create_response = await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "E2E Tool with Variables",
                "entry": "prepare",
                "nodes": {
                    "prepare": {
                        "type": "code",
                        "code": "async def run(args, state):\n    state['order_id'] = '12345'\n    return state",
                    },
                    "format": {
                        "type": "code",
                        "code": "async def run(args, state):\n    return {'formatted_order': f\"{args['prefix']}{args['id']}\"}",
                        "input_mapping": {"prefix": "@var:order_prefix", "id": "@state:order_id"},
                    },
                    "finish": {
                        "type": "code",
                        "code": "async def run(args, state):\n    state['response'] = f\"Order: {state['formatted_order']}\"\n    return state",
                    },
                },
                "edges": [
                    {"from_node": "prepare", "to_node": "format"},
                    {"from_node": "format", "to_node": "finish"},
                    {"from_node": "finish", "to_node": None},
                ],
                "variables": {"order_prefix": "ORD-"},
            },
        )
        assert create_response.status_code == 200
        exec_response = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": f"test-{unique_id}",
                "method": "message/send",
                "params": {"message": _msg("format order")},
            },
        )
        assert exec_response.status_code == 200
        task = get_task_from_response(exec_response.json())
        assert get_task_state(task) == "completed"
        response_text = get_task_response(task)
        assert "ORD-12345" in response_text
        await client.delete(f"/flows/api/v1/{flow_id}")

    @pytest.mark.asyncio
    async def test_tool_node_chain(self, client, unique_id):
        """E2E: Цепочка CodeNode через A2A."""
        flow_id = f"e2e_tool_chain_{unique_id}"
        create_response = await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "E2E Tool Chain",
                "entry": "init",
                "nodes": {
                    "init": {
                        "type": "code",
                        "code": "async def run(args, state):\n    state['input'] = 10\n    return state",
                    },
                    "double": {
                        "type": "code",
                        "code": "async def run(args, state):\n    return {'doubled': args['x'] * 2}",
                        "input_mapping": {"x": "@state:input"},
                    },
                    "square": {
                        "type": "code",
                        "code": "async def run(args, state):\n    return {'squared': args['x'] ** 2}",
                        "input_mapping": {"x": "@state:doubled"},
                    },
                    "finish": {
                        "type": "code",
                        "code": "async def run(args, state):\n    state['response'] = f\"Result: {state['squared']}\"\n    return state",
                    },
                },
                "edges": [
                    {"from_node": "init", "to_node": "double"},
                    {"from_node": "double", "to_node": "square"},
                    {"from_node": "square", "to_node": "finish"},
                    {"from_node": "finish", "to_node": None},
                ],
            },
        )
        assert create_response.status_code == 200
        exec_response = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": f"test-{unique_id}",
                "method": "message/send",
                "params": {"message": _msg("chain")},
            },
        )
        assert exec_response.status_code == 200
        task = get_task_from_response(exec_response.json())
        assert get_task_state(task) == "completed"
        response_text = get_task_response(task)
        assert "400" in response_text
        await client.delete(f"/flows/api/v1/{flow_id}")

    @pytest.mark.asyncio
    async def test_tool_node_with_nested_state(self, client, unique_id):
        """E2E: CodeNode с вложенными путями в state через A2A."""
        flow_id = f"e2e_tool_nested_{unique_id}"
        create_response = await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "E2E Tool Nested State",
                "entry": "prepare",
                "nodes": {
                    "prepare": {
                        "type": "code",
                        "code": "async def run(args, state):\n    state['user'] = {'name': 'Иван', 'email': 'ivan@test.com'}\n    state['config'] = {'template': 'Привет, {name}!'}\n    return state",
                    },
                    "greet": {
                        "type": "code",
                        "code": "async def run(args, state):\n    return {'greeting': args['template'].format(name=args['name'])}",
                        "input_mapping": {
                            "name": "@state:user.name",
                            "template": "@state:config.template",
                        },
                    },
                    "finish": {
                        "type": "code",
                        "code": "async def run(args, state):\n    state['response'] = state['greeting']\n    return state",
                    },
                },
                "edges": [
                    {"from_node": "prepare", "to_node": "greet"},
                    {"from_node": "greet", "to_node": "finish"},
                    {"from_node": "finish", "to_node": None},
                ],
            },
        )
        assert create_response.status_code == 200
        exec_response = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": f"test-{unique_id}",
                "method": "message/send",
                "params": {"message": _msg("greet")},
            },
        )
        assert exec_response.status_code == 200
        task = get_task_from_response(exec_response.json())
        assert get_task_state(task) == "completed"
        response_text = get_task_response(task)
        assert "Привет, Иван!" in response_text
        await client.delete(f"/flows/api/v1/{flow_id}")

    @pytest.mark.asyncio
    async def test_conditional_routing_to_tool_node(self, client, unique_id):
        """E2E: Условный переход к CodeNode через A2A."""
        flow_id = f"e2e_tool_condition_{unique_id}"
        create_response = await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "E2E Conditional Tool",
                "entry": "classify",
                "nodes": {
                    "classify": {
                        "type": "code",
                        "code": "async def run(args, state):\n    content = state.get('content', '').lower()\n    state['route'] = 'calc' if 'calc' in content else 'skip'\n    state['a'] = 2\n    state['b'] = 2\n    return state",
                    },
                    "calculate": {
                        "type": "code",
                        "code": "async def run(args, state):\n    return {'result': args['x'] + args['y']}",
                        "input_mapping": {"x": "@state:a", "y": "@state:b"},
                    },
                    "skip": {
                        "type": "code",
                        "code": "async def run(args, state):\n    state['result'] = 'skipped'\n    return state",
                    },
                    "finish": {
                        "type": "code",
                        "code": "async def run(args, state):\n    state['response'] = f\"Result: {state['result']}\"\n    return state",
                    },
                },
                "edges": [
                    {
                        "from_node": "classify",
                        "to_node": "calculate",
                        "condition": {
                            "type": "simple",
                            "variable": "route",
                            "operator": "==",
                            "value": "calc",
                        },
                    },
                    {
                        "from_node": "classify",
                        "to_node": "skip",
                        "condition": {
                            "type": "simple",
                            "variable": "route",
                            "operator": "==",
                            "value": "skip",
                        },
                    },
                    {"from_node": "calculate", "to_node": "finish"},
                    {"from_node": "skip", "to_node": "finish"},
                    {"from_node": "finish", "to_node": None},
                ],
            },
        )
        assert create_response.status_code == 200
        exec_response1 = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": f"test1-{unique_id}",
                "method": "message/send",
                "params": {"message": _msg("calculate please")},
            },
        )
        assert exec_response1.status_code == 200
        task1 = get_task_from_response(exec_response1.json())
        assert "4" in get_task_response(task1)
        exec_response2 = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": f"test2-{unique_id}",
                "method": "message/send",
                "params": {"message": _msg("something else")},
            },
        )
        assert exec_response2.status_code == 200
        task2 = get_task_from_response(exec_response2.json())
        assert "skipped" in get_task_response(task2)
        await client.delete(f"/flows/api/v1/{flow_id}")
