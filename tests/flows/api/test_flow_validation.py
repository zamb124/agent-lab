"""
Тесты для API валидации flow.

POST /api/v1/flows/validate - валидация графа без сохранения.

Тестируемые проверки:
1. Структура графа (entry, edges, достижимость)
2. Ссылки на агенты, tools, subflows
3. Переменные @var:
4. Парсинг inline code
5. Попытка сборки Agent
"""

import json
from pathlib import Path

import pytest

BUNDLES_DIR = Path(__file__).parent.parent.parent.parent / "apps" / "flows" / "bundles"


def simple_condition(variable: str, operator: str, value: object) -> dict[str, object]:
    return {"type": "simple", "variable": variable, "operator": operator, "value": value}


class TestFlowValidationStructure:
    """Тесты валидации структуры графа."""

    @pytest.mark.asyncio
    async def test_validate_valid_flow(self, client, app):
        """Валидный flow проходит проверку."""
        response = await client.post(
            "/flows/api/v1/flows/validate",
            json={
                "nodes": {"main": {"type": "llm_node", "prompt": "Test agent", "tools": []}},
                "edges": [{"from_node": "main", "to_node": None}],
                "entry": "main",
                "variables": {},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert len([e for e in data["errors"] if e["severity"] == "error"]) == 0

    @pytest.mark.asyncio
    async def test_validate_missing_entry(self, client, app):
        """Ошибка при отсутствии entry."""
        response = await client.post(
            "/flows/api/v1/flows/validate",
            json={
                "nodes": {"main": {"type": "llm_node", "prompt": "Test"}},
                "edges": [],
                "entry": "",
                "variables": {},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        error_codes = [e["code"] for e in data["errors"]]
        assert "missing_entry" in error_codes

    @pytest.mark.asyncio
    async def test_validate_entry_not_in_nodes(self, client, app):
        """Ошибка если entry не существует в nodes."""
        response = await client.post(
            "/flows/api/v1/flows/validate",
            json={
                "nodes": {"main": {"type": "llm_node", "prompt": "Test"}},
                "edges": [],
                "entry": "nonexistent_node",
                "variables": {},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        error_codes = [e["code"] for e in data["errors"]]
        assert "entry_not_found" in error_codes

    @pytest.mark.asyncio
    async def test_validate_edge_from_not_found(self, client, app):
        """Ошибка если edge.from_node ссылается на несуществующую ноду."""
        response = await client.post(
            "/flows/api/v1/flows/validate",
            json={
                "nodes": {"main": {"type": "llm_node", "prompt": "Test"}},
                "edges": [{"from_node": "nonexistent", "to_node": "main"}],
                "entry": "main",
                "variables": {},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        error_codes = [e["code"] for e in data["errors"]]
        assert "edge_from_not_found" in error_codes

    @pytest.mark.asyncio
    async def test_validate_edge_to_not_found(self, client, app):
        """Ошибка если edge.to_node ссылается на несуществующую ноду."""
        response = await client.post(
            "/flows/api/v1/flows/validate",
            json={
                "nodes": {"main": {"type": "llm_node", "prompt": "Test"}},
                "edges": [{"from_node": "main", "to_node": "nonexistent"}],
                "entry": "main",
                "variables": {},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        error_codes = [e["code"] for e in data["errors"]]
        assert "edge_to_not_found" in error_codes

    @pytest.mark.asyncio
    async def test_validate_unreachable_nodes_warning(self, client, app):
        """Предупреждение о недостижимых нодах."""
        response = await client.post(
            "/flows/api/v1/flows/validate",
            json={
                "nodes": {
                    "main": {"type": "llm_node", "prompt": "Test"},
                    "orphan": {"type": "llm_node", "prompt": "Orphan node"},
                },
                "edges": [{"from_node": "main", "to_node": None}],
                "entry": "main",
                "variables": {},
            },
        )
        assert response.status_code == 200
        data = response.json()
        warnings = [e for e in data["errors"] if e["severity"] == "warning"]
        warning_codes = [w["code"] for w in warnings]
        assert "unreachable_nodes" in warning_codes
        unreachable_warning = next((w for w in warnings if w["code"] == "unreachable_nodes"))
        assert "orphan" in unreachable_warning["details"]["unreachable"]


class TestFlowValidationReferences:
    """Тесты валидации ссылок на сущности."""

    @pytest.mark.asyncio
    async def test_validate_existing_node_id(self, client, app, test_node_in_db):
        """Существующий node_id проходит валидацию."""
        response = await client.post(
            "/flows/api/v1/flows/validate",
            json={
                "nodes": {"main": {"type": "llm_node", "node_id": test_node_in_db}},
                "edges": [{"from_node": "main", "to_node": None}],
                "entry": "main",
                "variables": {},
            },
        )
        assert response.status_code == 200
        data = response.json()
        error_codes = [e["code"] for e in data["errors"] if e["severity"] == "error"]
        assert "node_not_found" not in error_codes

    @pytest.mark.asyncio
    async def test_validate_nonexistent_node_id(self, client, app):
        """Ошибка при несуществующем node_id."""
        response = await client.post(
            "/flows/api/v1/flows/validate",
            json={
                "nodes": {"main": {"type": "llm_node", "node_id": "nonexistent_node_xyz_12345"}},
                "edges": [{"from_node": "main", "to_node": None}],
                "entry": "main",
                "variables": {},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        error_codes = [e["code"] for e in data["errors"]]
        assert "node_not_found" in error_codes

    @pytest.mark.asyncio
    async def test_validate_existing_tool(self, client, app):
        """Существующий tool проходит валидацию."""
        response = await client.post(
            "/flows/api/v1/flows/validate",
            json={
                "nodes": {"main": {"type": "llm_node", "prompt": "Test", "tools": ["calculator"]}},
                "edges": [{"from_node": "main", "to_node": None}],
                "entry": "main",
                "variables": {},
            },
        )
        assert response.status_code == 200
        data = response.json()
        error_codes = [e["code"] for e in data["errors"] if e["severity"] == "error"]
        assert "tool_not_found" not in error_codes

    @pytest.mark.asyncio
    async def test_validate_nonexistent_tool(self, client, app):
        """Ошибка при несуществующем tool."""
        response = await client.post(
            "/flows/api/v1/flows/validate",
            json={
                "nodes": {
                    "main": {
                        "type": "llm_node",
                        "prompt": "Test",
                        "tools": ["nonexistent_tool_xyz_12345"],
                    }
                },
                "edges": [{"from_node": "main", "to_node": None}],
                "entry": "main",
                "variables": {},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        error_codes = [e["code"] for e in data["errors"]]
        assert "tool_not_found" in error_codes

    @pytest.mark.asyncio
    async def test_validate_inline_tool_skipped(self, client, app):
        """Inline tool (dict) не проверяется как ссылка."""
        response = await client.post(
            "/flows/api/v1/flows/validate",
            json={
                "nodes": {
                    "main": {
                        "type": "llm_node",
                        "prompt": "Test",
                        "tools": [
                            {
                                "tool_id": "inline_test",
                                "code": "async def run(args, state): return 'ok'",
                            }
                        ],
                    }
                },
                "edges": [{"from_node": "main", "to_node": None}],
                "entry": "main",
                "variables": {},
            },
        )
        assert response.status_code == 200
        data = response.json()
        error_codes = [e["code"] for e in data["errors"] if e["severity"] == "error"]
        assert "tool_not_found" not in error_codes

    @pytest.mark.asyncio
    async def test_validate_tool_node_with_valid_tool_id(self, client, app):
        """type: tool с существующим tool_id."""
        response = await client.post(
            "/flows/api/v1/flows/validate",
            json={
                "nodes": {"main": {"type": "code", "tool_id": "calculator"}},
                "edges": [{"from_node": "main", "to_node": None}],
                "entry": "main",
                "variables": {},
            },
        )
        assert response.status_code == 200
        data = response.json()
        error_codes = [e["code"] for e in data["errors"] if e["severity"] == "error"]
        assert "tool_not_found" not in error_codes

    @pytest.mark.asyncio
    async def test_validate_tool_node_with_invalid_tool_id(self, client, app):
        """type: tool с несуществующим tool_id."""
        response = await client.post(
            "/flows/api/v1/flows/validate",
            json={
                "nodes": {"main": {"type": "code", "tool_id": "nonexistent_tool_xyz_12345"}},
                "edges": [{"from_node": "main", "to_node": None}],
                "entry": "main",
                "variables": {},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        error_codes = [e["code"] for e in data["errors"]]
        assert "tool_not_found" in error_codes

    @pytest.mark.asyncio
    async def test_validate_tool_node_with_inline_code(self, client, app):
        """type: tool с inline code не проверяет tool_id."""
        response = await client.post(
            "/flows/api/v1/flows/validate",
            json={
                "nodes": {
                    "main": {"type": "code", "code": "async def run(args, state): return 'ok'"}
                },
                "edges": [{"from_node": "main", "to_node": None}],
                "entry": "main",
                "variables": {},
            },
        )
        assert response.status_code == 200
        data = response.json()
        error_codes = [e["code"] for e in data["errors"] if e["severity"] == "error"]
        assert "tool_not_found" not in error_codes

    @pytest.mark.asyncio
    async def test_validate_agent_not_found(self, client, app):
        """type: agent с несуществующим flow_id."""
        response = await client.post(
            "/flows/api/v1/flows/validate",
            json={
                "nodes": {"main": {"type": "flow", "flow_id": "nonexistent_agent_xyz_12345"}},
                "edges": [{"from_node": "main", "to_node": None}],
                "entry": "main",
                "variables": {},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        error_codes = [e["code"] for e in data["errors"]]
        assert "flow_not_found" in error_codes

    @pytest.mark.asyncio
    async def test_validate_remote_flow_no_target(self, client, app):
        """remote_flow без flow_id и url."""
        response = await client.post(
            "/flows/api/v1/flows/validate",
            json={
                "nodes": {"main": {"type": "remote_flow"}},
                "edges": [{"from_node": "main", "to_node": None}],
                "entry": "main",
                "variables": {},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        error_codes = [e["code"] for e in data["errors"]]
        assert "remote_flow_no_target" in error_codes


class TestFlowValidationVariables:
    """Тесты валидации переменных @var:."""

    @pytest.mark.asyncio
    async def test_validate_defined_variable(self, client, app):
        """Переменная объявлена в variables - OK."""
        response = await client.post(
            "/flows/api/v1/flows/validate",
            json={
                "nodes": {
                    "main": {
                        "type": "llm_node",
                        "prompt": "Test",
                        "input_mapping": {"api_key": "@var:my_api_key"},
                    }
                },
                "edges": [{"from_node": "main", "to_node": None}],
                "entry": "main",
                "variables": {"my_api_key": "secret123"},
            },
        )
        assert response.status_code == 200
        data = response.json()
        error_codes = [e["code"] for e in data["errors"] if e["severity"] == "error"]
        assert "undefined_variable" not in error_codes
        assert "my_api_key" in data["var_keys_used"]

    @pytest.mark.asyncio
    async def test_validate_undefined_variable(self, client, app):
        """Переменная НЕ объявлена в variables - ошибка."""
        response = await client.post(
            "/flows/api/v1/flows/validate",
            json={
                "nodes": {
                    "main": {
                        "type": "llm_node",
                        "prompt": "Test",
                        "input_mapping": {"api_key": "@var:undefined_var_xyz"},
                    }
                },
                "edges": [{"from_node": "main", "to_node": None}],
                "entry": "main",
                "variables": {},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        error_codes = [e["code"] for e in data["errors"]]
        assert "undefined_variable" in error_codes

    @pytest.mark.asyncio
    async def test_validate_variable_value_can_reference_company_variable(self, client, app):
        """FlowVariableConfig.value с @var: ссылается на company variable, не на эту же секцию."""
        response = await client.post(
            "/flows/api/v1/flows/validate",
            json={
                "nodes": {
                    "main": {
                        "type": "llm_node",
                        "prompt": "Test",
                        "input_mapping": {"bot_token": "@var:telegram_mirror_bot_token"},
                    }
                },
                "edges": [{"from_node": "main", "to_node": None}],
                "entry": "main",
                "variables": {
                    "telegram_mirror_bot_token": {
                        "value": "@var:telegram_notify_bot_token",
                        "secret": True,
                    }
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        error_codes = [e["code"] for e in data["errors"] if e["severity"] == "error"]
        assert "undefined_variable" not in error_codes
        assert "telegram_mirror_bot_token" in data["var_keys_used"]
        assert "telegram_notify_bot_token" in data["var_keys_used"]

    @pytest.mark.asyncio
    async def test_validate_variable_in_url(self, client, app):
        """@var: в url remote_flow."""
        response = await client.post(
            "/flows/api/v1/flows/validate",
            json={
                "nodes": {
                    "main": {
                        "type": "remote_flow",
                        "url": "https://api.example.com/@var:api_version/endpoint",
                    }
                },
                "edges": [{"from_node": "main", "to_node": None}],
                "entry": "main",
                "variables": {"api_version": "v2"},
            },
        )
        assert response.status_code == 200
        data = response.json()
        error_codes = [e["code"] for e in data["errors"] if e["severity"] == "error"]
        assert "undefined_variable" not in error_codes

    @pytest.mark.asyncio
    async def test_validate_variable_in_headers(self, client, app):
        """@var: в headers."""
        response = await client.post(
            "/flows/api/v1/flows/validate",
            json={
                "nodes": {
                    "main": {
                        "type": "external_api",
                        "url": "https://api.example.com",
                        "headers": {"Authorization": "Bearer @var:api_token"},
                    }
                },
                "edges": [{"from_node": "main", "to_node": None}],
                "entry": "main",
                "variables": {},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        error_codes = [e["code"] for e in data["errors"]]
        assert "undefined_variable" in error_codes


class TestFlowValidationInlineCode:
    """Тесты парсинга inline code."""

    @pytest.mark.asyncio
    async def test_validate_inline_code_state_keys_extracted(self, client, app):
        """Извлечение state ключей из inline code."""
        response = await client.post(
            "/flows/api/v1/flows/validate",
            json={
                "nodes": {
                    "main": {
                        "type": "code",
                        "code": "async def run(args, state):\n    content = state.get('content', '')\n    state['result'] = content.upper()\n    return state",
                    }
                },
                "edges": [{"from_node": "main", "to_node": None}],
                "entry": "main",
                "variables": {},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "content" in data["state_keys_used"]
        assert "result" in data["state_keys_used"]

    @pytest.mark.asyncio
    async def test_validate_inline_code_info_message(self, client, app):
        """Info сообщение о найденных state ключах."""
        response = await client.post(
            "/flows/api/v1/flows/validate",
            json={
                "nodes": {
                    "classifier": {
                        "type": "code",
                        "code": "async def run(args, state):\n    content = state['content'].lower()\n    if 'order' in content:\n        state['route'] = 'order'\n    return state",
                    }
                },
                "edges": [{"from_node": "classifier", "to_node": None}],
                "entry": "classifier",
                "variables": {},
            },
        )
        assert response.status_code == 200
        data = response.json()
        info_messages = [e for e in data["errors"] if e["severity"] == "info"]
        assert len(info_messages) > 0
        code_info = [e for e in info_messages if e["code"] == "inline_code_state_keys"]
        assert len(code_info) > 0


class TestFlowValidationExampleGraph:
    """Тесты на примере agents/example_graph."""

    @pytest.mark.asyncio
    async def test_validate_example_graph_flow(self, client, app):
        """Валидация example_graph flow."""
        flow_path = BUNDLES_DIR / "example_graph" / "flow.json"
        with open(flow_path) as f:
            flow_config = json.load(f)
        response = await client.post(
            "/flows/api/v1/flows/validate",
            json={
                "nodes": flow_config["nodes"],
                "edges": flow_config["edges"],
                "entry": flow_config["entry"],
                "variables": flow_config.get("variables", {}),
                "flow_id": flow_config["flow_id"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        errors = [e for e in data["errors"] if e["severity"] == "error"]
        for err in errors:
            print(f"Error: {err['code']} - {err['message']}")
        structure_errors = [
            e
            for e in errors
            if e["code"]
            in ["missing_entry", "entry_not_found", "edge_from_not_found", "edge_to_not_found"]
        ]
        assert len(structure_errors) == 0, f"Structure errors: {structure_errors}"

    @pytest.mark.asyncio
    async def test_validate_example_graph_has_inline_code(self, client, app):
        """example_graph содержит inline code - должны извлечься state ключи."""
        flow_path = BUNDLES_DIR / "example_graph" / "flow.json"
        with open(flow_path) as f:
            flow_config = json.load(f)
        response = await client.post(
            "/flows/api/v1/flows/validate",
            json={
                "nodes": flow_config["nodes"],
                "edges": flow_config["edges"],
                "entry": flow_config["entry"],
                "variables": flow_config.get("variables", {}),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "content" in data["state_keys_used"]
        assert "route" in data["state_keys_used"]

    @pytest.mark.asyncio
    async def test_validate_example_graph_variables(self, client, app):
        """example_graph использует @var: - проверка variables."""
        flow_path = BUNDLES_DIR / "example_graph" / "flow.json"
        with open(flow_path) as f:
            flow_config = json.load(f)
        response = await client.post(
            "/flows/api/v1/flows/validate",
            json={
                "nodes": flow_config["nodes"],
                "edges": flow_config["edges"],
                "entry": flow_config["entry"],
                "variables": flow_config.get("variables", {}),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "company_name" in data["var_keys_used"]
        assert "support_contacts" in data["var_keys_used"]


class TestFlowValidationComplexCases:
    """Сложные тестовые кейсы."""

    @pytest.mark.asyncio
    async def test_validate_graph_with_conditions(self, client, app):
        """Граф с условными переходами."""
        response = await client.post(
            "/flows/api/v1/flows/validate",
            json={
                "nodes": {
                    "router": {
                        "type": "code",
                        "code": "async def run(args, state):\n    state['route'] = 'a' if state.get('flag') else 'b'\n    return state",
                    },
                    "handler_a": {"type": "llm_node", "prompt": "Handler A"},
                    "handler_b": {"type": "llm_node", "prompt": "Handler B"},
                    "final": {"type": "llm_node", "prompt": "Final"},
                },
                "edges": [
                    {
                        "from_node": "router",
                        "to_node": "handler_a",
                        "condition": simple_condition("route", "==", "a"),
                    },
                    {
                        "from_node": "router",
                        "to_node": "handler_b",
                        "condition": simple_condition("route", "==", "b"),
                    },
                    {"from_node": "handler_a", "to_node": "final"},
                    {"from_node": "handler_b", "to_node": "final"},
                    {"from_node": "final", "to_node": None},
                ],
                "entry": "router",
                "variables": {},
            },
        )
        assert response.status_code == 200
        data = response.json()
        errors = [e for e in data["errors"] if e["severity"] == "error"]
        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_validate_graph_with_multiple_exits(self, client, app):
        """Граф с несколькими выходами."""
        response = await client.post(
            "/flows/api/v1/flows/validate",
            json={
                "nodes": {
                    "router": {
                        "type": "code",
                        "code": "async def run(args, state): state['route'] = 'a'; return state",
                    },
                    "exit_a": {"type": "llm_node", "prompt": "Exit A"},
                    "exit_b": {"type": "llm_node", "prompt": "Exit B"},
                },
                "edges": [
                    {
                        "from_node": "router",
                        "to_node": "exit_a",
                        "condition": simple_condition("route", "==", "a"),
                    },
                    {
                        "from_node": "router",
                        "to_node": "exit_b",
                        "condition": simple_condition("route", "==", "b"),
                    },
                    {"from_node": "exit_a", "to_node": None},
                    {"from_node": "exit_b", "to_node": None},
                ],
                "entry": "router",
                "variables": {},
            },
        )
        assert response.status_code == 200
        data = response.json()
        errors = [e for e in data["errors"] if e["severity"] == "error"]
        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_validate_empty_nodes(self, client, app):
        """Пустой граф - ошибка."""
        response = await client.post(
            "/flows/api/v1/flows/validate",
            json={"nodes": {}, "edges": [], "entry": "main", "variables": {}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        error_codes = [e["code"] for e in data["errors"]]
        assert "entry_not_found" in error_codes

    @pytest.mark.asyncio
    async def test_validate_nested_input_mapping(self, client, app):
        """Вложенный input_mapping с @var:."""
        response = await client.post(
            "/flows/api/v1/flows/validate",
            json={
                "nodes": {
                    "main": {
                        "type": "llm_node",
                        "prompt": "Test",
                        "input_mapping": {
                            "config": {"api_key": "@var:api_key", "settings": {"mode": "@var:mode"}}
                        },
                    }
                },
                "edges": [{"from_node": "main", "to_node": None}],
                "entry": "main",
                "variables": {"api_key": "secret"},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        undefined_errors = [e for e in data["errors"] if e["code"] == "undefined_variable"]
        assert len(undefined_errors) > 0
        assert "api_key" in data["var_keys_used"]
        assert "mode" in data["var_keys_used"]

    @pytest.mark.asyncio
    async def test_validate_build_failure(self, client, app):
        """Unknown node type rejected at strict API contract boundary."""
        response = await client.post(
            "/flows/api/v1/flows/validate",
            json={
                "nodes": {"main": {"type": "unknown_type_xyz", "prompt": "Test"}},
                "edges": [{"from_node": "main", "to_node": None}],
                "entry": "main",
                "variables": {},
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_validate_agent_as_tool_reference(self, client, app, test_agent_for_tool):
        """Агент как tool."""
        response = await client.post(
            "/flows/api/v1/flows/validate",
            json={
                "nodes": {
                    "main": {"type": "llm_node", "prompt": "Test", "tools": [test_agent_for_tool]}
                },
                "edges": [{"from_node": "main", "to_node": None}],
                "entry": "main",
                "variables": {},
            },
        )
        assert response.status_code == 200
        data = response.json()
        error_codes = [e["code"] for e in data["errors"] if e["severity"] == "error"]
        assert "tool_not_found" not in error_codes
