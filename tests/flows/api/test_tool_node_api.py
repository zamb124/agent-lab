"""
API тесты для CodeNode.

Тестирует создание flow с type: tool через API.
"""

import pytest


class TestCodeNodeFlowAPI:
    """Тесты создания flow с CodeNode через API."""

    @pytest.mark.asyncio
    async def test_create_flow_with_inline_tool_node(self, client, app, unique_id):
        """Создание flow с inline CodeNode."""
        flow_id = f"test_tool_inline_{unique_id}"

        response = await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Agent with Inline Tool",
                "entry": "calculator",
                "nodes": {
                    "calculator": {
                        "type": "code",
                        "code": "def execute(args, state):\n    return {'sum': args['a'] + args['b']}",
                        "args_schema": {
                            "a": {"type": "integer", "description": "First number"},
                            "b": {"type": "integer", "description": "Second number"},
                        },
                        "input_mapping": {
                            "a": "@state:num1",
                            "b": "@state:num2",
                        },
                    }
                },
                "edges": [{"from": "calculator", "to": None}],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["flow_id"] == flow_id
        assert "calculator" in data["nodes"]
        assert data["nodes"]["calculator"]["type"] == "code"

        # Cleanup
        await client.delete(f"/flows/api/v1/{flow_id}")

    @pytest.mark.asyncio
    async def test_create_flow_with_existing_tool(self, client, app, unique_id):
        """Создание flow с существующим tool_id (calculator)."""
        flow_id = f"test_tool_existing_{unique_id}"

        response = await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Agent with Existing Tool",
                "entry": "calc",
                "nodes": {
                    "calc": {
                        "type": "code",
                        "tool_id": "calculator",
                        "input_mapping": {
                            "expression": "@state:expr",
                        },
                        "output_key": "result",
                    }
                },
                "edges": [{"from": "calc", "to": None}],
            },
        )
        assert response.status_code == 200, f"Expected 200 but got {response.status_code}: {response.text}"
        data = response.json()
        assert data["flow_id"] == flow_id

        # Cleanup
        await client.delete(f"/flows/api/v1/{flow_id}")

    @pytest.mark.asyncio
    async def test_create_flow_with_invalid_tool_id(self, client, app, unique_id):
        """Ошибка при создании flow с несуществующим tool_id."""
        flow_id = f"test_tool_invalid_{unique_id}"

        response = await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Agent with Invalid Tool",
                "entry": "bad_tool",
                "nodes": {
                    "bad_tool": {
                        "type": "code",
                        "tool_id": "nonexistent_tool_xyz",
                        "input_mapping": {"x": 1},
                    }
                },
                "edges": [{"from": "bad_tool", "to": None}],
            },
        )
        assert response.status_code == 400
        assert "nonexistent_tool_xyz" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_flow_with_tool_and_var_mapping(self, client, app, unique_id):
        """Создание flow с CodeNode и @var: маппингом."""
        flow_id = f"test_tool_var_{unique_id}"

        response = await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Agent with Tool and Variables",
                "entry": "formatter",
                "nodes": {
                    "formatter": {
                        "type": "code",
                        "code": "def execute(args, state):\n    return f\"{args['prefix']}{args['value']}\"",
                        "input_mapping": {
                            "prefix": "@var:order_prefix",
                            "value": "@state:order_id",
                        },
                        "output_key": "formatted",
                    }
                },
                "edges": [{"from": "formatter", "to": None}],
                "variables": {"order_prefix": "ORD-"},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["flow_id"] == flow_id
        # Переменные могут возвращаться как объекты с полем value
        var_value = data["variables"]["order_prefix"]
        if isinstance(var_value, dict):
            assert var_value["value"] == "ORD-"
        else:
            assert var_value == "ORD-"

        # Cleanup
        await client.delete(f"/flows/api/v1/{flow_id}")

    @pytest.mark.asyncio
    async def test_create_flow_with_tool_chain(self, client, app, unique_id):
        """Создание flow с цепочкой CodeNode."""
        flow_id = f"test_tool_chain_{unique_id}"

        response = await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Agent with Tool Chain",
                "entry": "step1",
                "nodes": {
                    "step1": {
                        "type": "code",
                        "code": "def execute(args, state):\n    return args['x'] * 2",
                        "input_mapping": {"x": "@state:input"},
                        "output_key": "doubled",
                    },
                    "step2": {
                        "type": "code",
                        "code": "def execute(args, state):\n    return args['a'] + args['b']",
                        "input_mapping": {
                            "a": "@state:doubled",
                            "b": 100,
                        },
                        "output_key": "final",
                    },
                },
                "edges": [
                    {"from": "step1", "to": "step2"},
                    {"from": "step2", "to": None},
                ],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["flow_id"] == flow_id
        assert len(data["nodes"]) == 2

        # Cleanup
        await client.delete(f"/flows/api/v1/{flow_id}")


class TestAgentWithInlineToolAPI:
    """Тесты создания агента с inline tools через API."""

    @pytest.mark.asyncio
    async def test_create_flow_with_llm_node_inline_tools(self, client, app, unique_id):
        """Создание flow с llm_node и inline tools."""
        flow_id = f"test_agent_inline_tools_{unique_id}"

        response = await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Agent with Inline Tools Agent",
                "entry": "agent",
                "nodes": {
                    "agent": {
                        "type": "llm_node",
                        "prompt": "You are a calculator assistant.",
                        "tools": [
                            "calculator",
                            {
                                "tool_id": "custom_formatter",
                                "description": "Formats a greeting",
                                "args_schema": {
                                    "name": {"type": "string", "description": "Name to greet"},
                                },
                                "code": "def execute(args, state):\n    return f\"Hello, {args['name']}!\"",
                            },
                        ],
                        "llm": {"model": "gpt-4o", "temperature": 0.2},
                    }
                },
                "edges": [{"from": "agent", "to": None}],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["flow_id"] == flow_id

        # Cleanup
        await client.delete(f"/flows/api/v1/{flow_id}")

    @pytest.mark.asyncio
    async def test_create_flow_with_mixed_tools(self, client, app, unique_id, auth_headers_system):
        """Создание flow с llm_node со смешанными tools."""
        flow_id = f"test_mixed_tools_{unique_id}"

        response = await client.post(
            "/flows/api/v1/flows/",
            headers=auth_headers_system,
            json={
                "flow_id": flow_id,
                "name": "Agent with Mixed Tools",
                "entry": "main",
                "nodes": {
                    "main": {
                        "type": "llm_node",
                        "prompt": "Assistant with multiple tools",
                        "tools": [
                            "calculator",
                            "ask_user",
                            {
                                "tool_id": "inline_double",
                                "code": "def execute(args, state):\n    return args['x'] * 2",
                                "args_schema": {
                                    "x": {"type": "integer", "description": "Number to double"},
                                },
                            },
                        ],
                    }
                },
                "edges": [{"from": "main", "to": None}],
            },
        )
        assert response.status_code == 200

        # Cleanup
        await client.delete(f"/flows/api/v1/{flow_id}")


class TestUpdateFlowWithCodeNode:
    """Тесты обновления flow с CodeNode."""

    @pytest.mark.asyncio
    async def test_update_flow_add_tool_node(self, client, app, unique_id, auth_headers_system):
        """Обновление flow: добавление CodeNode."""
        flow_id = f"test_update_tool_{unique_id}"

        # Создаем простой flow
        await client.post(
            "/flows/api/v1/flows/",
            json={
                "flow_id": flow_id,
                "name": "Simple Agent",
                "entry": "start",
                "nodes": {
                    "start": {
                        "type": "code",
                        "code": "def run(state):\n    state['value'] = 10\n    return state",
                    }
                },
                "edges": [{"from": "start", "to": None}],
            },
        )

        # Обновляем - добавляем CodeNode
        response = await client.put(
            f"/flows/api/v1/flows/{flow_id}",
            headers=auth_headers_system,
            json={
                "flow_id": flow_id,
                "name": "Updated Agent with Tool",
                "entry": "start",
                "nodes": {
                    "start": {
                        "type": "code",
                        "code": "def run(state):\n    state['value'] = 10\n    return state",
                    },
                    "process": {
                        "type": "code",
                        "code": "def execute(args, state):\n    return {'processed': args['x'] * 2}",
                        "input_mapping": {"x": "@state:value"},
                    },
                },
                "edges": [
                    {"from": "start", "to": "process"},
                    {"from": "process", "to": None},
                ],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "process" in data["nodes"]
        assert data["nodes"]["process"]["type"] == "code"

        # Cleanup
        await client.delete(f"/flows/api/v1/{flow_id}", headers=auth_headers_system)

