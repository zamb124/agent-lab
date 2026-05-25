"""
Strict CodeNode contract tests.

Every execution goes through the durable workflow harness. These tests must not
construct side-effect nodes without a runtime container and must not call
``node.run(state)`` directly.
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.models.enums import NodeType
from apps.flows.src.runtime.nodes import CodeNode, create_node
from core.state import ExecutionState
from core.types import JsonObject
from tests.flows.durable_runtime_harness import run_node, workflow_state


def code_node(container: FlowRuntimeContainer, node_id: str, config: JsonObject) -> CodeNode:
    if "type" in config:
        raise ValueError("test code node config must not override canonical node type")
    return CodeNode(
        node_id=node_id,
        config={"type": NodeType.CODE.value, **config},
        container=container,
    )


def state_for(flow_id: str, unique_id: str, **extra: object) -> ExecutionState:
    return workflow_state(flow_id=flow_id, unique_id=unique_id, **extra)


async def execute_node(
    *,
    container: FlowRuntimeContainer,
    node: CodeNode,
    flow_id: str,
    unique_id: str,
    **state_extra: object,
) -> ExecutionState:
    return await run_node(
        container=container,
        node=node,
        state=state_for(flow_id, unique_id, **state_extra),
    )


class TestCodeNode:
    @pytest.mark.asyncio
    async def test_tool_node_basic_execution(
        self,
        container: FlowRuntimeContainer,
        unique_id: str,
    ) -> None:
        node = code_node(
            container,
            "test_node",
            {
                "code": (
                    "async def run(args, state):\n"
                    '    return {"result": args.get("x", 0) + args.get("y", 0)}'
                ),
                "input_mapping": {"x": 10, "y": 20},
            },
        )

        result = await execute_node(
            container=container,
            node=node,
            flow_id="code_node_basic",
            unique_id=unique_id,
        )

        assert result.result == 30

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("input_mapping", "state_extra", "expected_field", "expected_value"),
        [
            (
                {"x": "@state:value_x", "y": "@state:value_y"},
                {"value_x": 5, "value_y": 15},
                "sum",
                20,
            ),
            (
                {"x": "@state:data.first", "y": "@state:data.second"},
                {"data": {"first": 100, "second": 200}},
                "sum",
                300,
            ),
            (
                {"x": "@var:multiplier", "y": "@state:value"},
                {"value": 10, "variables": {"multiplier": 5}},
                "sum",
                15,
            ),
            (
                {"x": 42, "y": 8},
                {},
                "sum",
                50,
            ),
        ],
    )
    async def test_tool_node_input_mapping_sources(
        self,
        container: FlowRuntimeContainer,
        unique_id: str,
        input_mapping: JsonObject,
        state_extra: dict[str, object],
        expected_field: str,
        expected_value: object,
    ) -> None:
        node = code_node(
            container,
            "mapping_node",
            {
                "code": 'async def run(args, state):\n    return {"sum": args["x"] + args["y"]}',
                "input_mapping": input_mapping,
            },
        )

        result = await execute_node(
            container=container,
            node=node,
            flow_id="code_node_mapping",
            unique_id=f"{unique_id}-{expected_value}",
            **state_extra,
        )

        assert result[expected_field] == expected_value

    @pytest.mark.asyncio
    async def test_tool_node_mixed_mapping(
        self,
        container: FlowRuntimeContainer,
        unique_id: str,
    ) -> None:
        node = code_node(
            container,
            "greeting_node",
            {
                "code": (
                    "async def run(args, state):\n"
                    "    return {'greeting': args['template'].format(name=args['name'])}"
                ),
                "input_mapping": {
                    "template": "Привет, {name}!",
                    "name": "@state:user.name",
                },
            },
        )

        result = await execute_node(
            container=container,
            node=node,
            flow_id="code_node_mixed_mapping",
            unique_id=unique_id,
            user={"name": "Иван"},
        )

        assert result.greeting == "Привет, Иван!"

    @pytest.mark.asyncio
    async def test_tool_node_scalar_result_goes_to_result_field(
        self,
        container: FlowRuntimeContainer,
        unique_id: str,
    ) -> None:
        node = code_node(
            container,
            "calculator_node",
            {
                "code": "async def run(args, state):\n    return args['x'] + args['y']",
                "input_mapping": {"x": 1, "y": 2},
            },
        )

        result = await execute_node(
            container=container,
            node=node,
            flow_id="code_node_scalar_result",
            unique_id=unique_id,
        )

        assert result.result == 3

    @pytest.mark.asyncio
    async def test_tool_node_preserves_existing_state(
        self,
        container: FlowRuntimeContainer,
        unique_id: str,
    ) -> None:
        node = code_node(
            container,
            "preserve_node",
            {
                "code": 'async def run(args, state):\n    return {"result": args["x"] + args["y"]}',
                "input_mapping": {"x": 1, "y": 2},
            },
        )

        result = await execute_node(
            container=container,
            node=node,
            flow_id="code_node_preserve",
            unique_id=unique_id,
            existing_field="value",
            another=123,
        )

        assert result.existing_field == "value"
        assert result.another == 123
        assert result.result == 3


class TestInlineCodeNode:
    @pytest.mark.asyncio
    async def test_inline_tool_basic(
        self,
        container: FlowRuntimeContainer,
        unique_id: str,
    ) -> None:
        node = code_node(
            container,
            "inline_node",
            {
                "code": "async def run(args, state):\n    return {'sum': args['a'] + args['b']}",
                "input_mapping": {"a": 100, "b": 200},
            },
        )

        result = await execute_node(
            container=container,
            node=node,
            flow_id="code_node_inline",
            unique_id=unique_id,
        )

        assert result.sum == 300

    @pytest.mark.asyncio
    async def test_inline_tool_with_state_access(
        self,
        container: FlowRuntimeContainer,
        unique_id: str,
    ) -> None:
        node = code_node(
            container,
            "reader_node",
            {
                "code": "async def run(args, state):\n    return {'secret_value': state['secret']}",
                "input_mapping": {},
            },
        )

        result = await execute_node(
            container=container,
            node=node,
            flow_id="code_node_state_access",
            unique_id=unique_id,
            secret="my_secret_value",
        )

        assert result.secret_value == "my_secret_value"

    @pytest.mark.asyncio
    async def test_inline_tool_with_var_mapping(
        self,
        container: FlowRuntimeContainer,
        unique_id: str,
    ) -> None:
        node = code_node(
            container,
            "greeting_node",
            {
                "code": (
                    "async def run(args, state):\n"
                    "    return {'message': f\"Добро пожаловать в {args['company']}, {args['user']}!\"}"
                ),
                "input_mapping": {
                    "company": "@var:company_name",
                    "user": "@state:user.name",
                },
            },
        )

        result = await execute_node(
            container=container,
            node=node,
            flow_id="code_node_var_mapping",
            unique_id=unique_id,
            user={"name": "Мария"},
            variables={"company_name": "Acme Corp"},
        )

        assert result.message == "Добро пожаловать в Acme Corp, Мария!"


class TestCreateNodeTool:
    @pytest.mark.asyncio
    async def test_create_node_inline_tool(
        self,
        container: FlowRuntimeContainer,
        unique_id: str,
    ) -> None:
        node_config: JsonObject = {
            "type": NodeType.CODE.value,
            "code": "async def run(args, state):\n    return {'doubled': args['x'] * 2}",
            "parameters_schema": {
                "type": "object",
                "properties": {"x": {"type": "integer", "description": "Число для удвоения"}},
                "required": ["x"],
            },
            "input_mapping": {"x": 5},
        }

        node = await create_node("double_node", node_config, container=container)

        assert isinstance(node, CodeNode)
        assert node.node_id == "double_node"
        result = await run_node(
            container=container,
            node=node,
            state=state_for("double_node_flow", unique_id),
        )
        assert result.doubled == 10

    @pytest.mark.asyncio
    async def test_create_node_inline_tool_with_mapping(
        self,
        container: FlowRuntimeContainer,
        unique_id: str,
    ) -> None:
        node_config: JsonObject = {
            "type": NodeType.CODE.value,
            "code": (
                "async def run(args, state):\n"
                "    return {'formatted_order': f\"{args['prefix']}{args['value']}\"}"
            ),
            "input_mapping": {"prefix": "@var:order_prefix", "value": "@state:order_id"},
        }

        node = await create_node("format_node", node_config, container=container)
        result = await run_node(
            container=container,
            node=node,
            state=state_for(
                "format_node_flow",
                unique_id,
                order_id="12345",
                variables={"order_prefix": "ORD-"},
            ),
        )

        assert result.formatted_order == "ORD-12345"


class TestCodeNodeNamedArguments:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("case_id", "code", "input_mapping", "state_extra", "expected"),
        [
            (
                "defaults",
                'def run(x=10, y=20, state=None):\n    return {"result": x + y}',
                {},
                {},
                30,
            ),
            (
                "explicit-values",
                'def run(x=10, y=20, state=None):\n    return {"result": x + y}',
                {"x": 5, "y": 15},
                {},
                20,
            ),
            (
                "partial-defaults",
                'def run(x=10, y=20, z=30, state=None):\n    return {"result": x + y + z}',
                {"x": 5},
                {},
                55,
            ),
            (
                "state-values",
                'def run(x=10, y=20, state=None):\n    return {"result": x + y}',
                {"x": "@state:value_x", "y": "@state:value_y"},
                {"value_x": 7, "value_y": 13},
                20,
            ),
            (
                "state-and-var-values",
                (
                    "def run(x=10, y=20, z=30, multiplier=1, state=None):\n"
                    '    return {"result": (x + y + z) * multiplier}'
                ),
                {"x": "@state:value_x", "y": "@var:value_y", "z": 100},
                {"value_x": 5, "variables": {"value_y": 15}},
                120,
            ),
            (
                "message-result",
                (
                    'def run(greeting="Hello", name="World", state=None):\n'
                    '    return {"message": f"{greeting}, {name}!"}'
                ),
                {"name": "@state:user_name"},
                {"user_name": "Иван"},
                "Hello, Иван!",
            ),
            (
                "list-result",
                (
                    'def run(items=None, prefix="Item", state=None):\n'
                    "    if items is None:\n"
                    "        items = []\n"
                    '    return {"formatted": [f"{prefix}: {item}" for item in items]}'
                ),
                {"items": "@state:item_list"},
                {"item_list": ["apple", "banana"]},
                ["Item: apple", "Item: banana"],
            ),
            (
                "dict-result",
                (
                    'def run(config=None, key="default", state=None):\n'
                    "    if config is None:\n"
                    "        config = {}\n"
                    '    return {"value": config[key]}'
                ),
                {"config": "@state:user_config"},
                {"user_config": {"default": "found", "other": "value"}},
                "found",
            ),
        ],
    )
    async def test_named_arguments(
        self,
        container: FlowRuntimeContainer,
        unique_id: str,
        case_id: str,
        code: str,
        input_mapping: JsonObject,
        state_extra: dict[str, object],
        expected: Any,
    ) -> None:
        node = code_node(
            container,
            "named_args_node",
            {"code": code, "input_mapping": input_mapping},
        )

        result = await execute_node(
            container=container,
            node=node,
            flow_id="code_node_named_args",
            unique_id=f"{unique_id}-{case_id}",
            **state_extra,
        )

        if "message" in result:
            assert result.message == expected
        elif "formatted" in result:
            assert result.formatted == expected
        elif "value" in result:
            assert result.value == expected
        else:
            assert result.result == expected
