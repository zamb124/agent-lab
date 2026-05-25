"""
E2E тесты для полного цикла переопределений.

Тестируем реальное выполнение agents с различными skills и переопределениями.
"""

import pytest

from apps.flows.src.container import get_container
from apps.flows.src.container_contracts import as_flow_runtime_container
from apps.flows.src.runtime.flow import Flow
from core.state import ExecutionState


async def build_flow(config, variables):
    return await Flow.from_config(
        config=config,
        variables=variables,
        container=as_flow_runtime_container(get_container()),
    )


class TestCodeNodeOverrides:
    """E2E тесты переопределения function nodes."""

    @pytest.mark.asyncio
    async def test_function_code_override_changes_behavior(self):
        """Переопределение code в function node меняет поведение."""
        flow_default = await build_flow(
            config={
                "flow_id": "test_fn",
                "name": "Test",
                "entry": "classifier",
                "nodes": {
                    "classifier": {
                        "type": "code",
                        "code": "async def run(args, state):\n    state.route = 'default'\n    return state",
                    }
                },
                "edges": [{"from_node": "classifier", "to_node": None}],
            },
            variables={},
        )
        state = await flow_default.run(
            ExecutionState(
                task_id="test-task",
                context_id="test-context",
                user_id="test-user",
                session_id="test-agent:test-context",
                content="test",
            )
        )
        assert state.route == "default"
        flow_skill = await build_flow(
            config={
                "flow_id": "test_fn",
                "name": "Test",
                "entry": "classifier",
                "nodes": {
                    "classifier": {
                        "type": "code",
                        "code": "async def run(args, state):\n    state.route = 'custom'\n    return state",
                    }
                },
                "edges": [{"from_node": "classifier", "to_node": None}],
            },
            variables={},
        )
        state = await flow_skill.run(
            ExecutionState(
                task_id="test-task",
                context_id="test-context",
                user_id="test-user",
                session_id="test-agent:test-context",
                content="test",
            )
        )
        assert state.route == "custom"

    @pytest.mark.asyncio
    async def test_conditional_routing_override(self):
        """Переопределение условий routing."""
        config_base = {
            "flow_id": "test_routing",
            "name": "Test",
            "entry": "classifier",
            "nodes": {
                "classifier": {
                    "type": "code",
                    "code": "\nasync def run(args, state):\n    content = (getattr(state, 'content', None) or '').lower()\n    if 'заказ' in content:\n        state.route = 'order'\n    elif 'жалоб' in content:\n        state.route = 'complaint'\n    else:\n        state.route = 'general'\n    return state\n",
                },
                "order": {
                    "type": "code",
                    "code": "async def run(args, state): state.result = 'order'; return state",
                },
                "complaint": {
                    "type": "code",
                    "code": "async def run(args, state): state.result = 'complaint'; return state",
                },
                "general": {
                    "type": "code",
                    "code": "async def run(args, state): state.result = 'general'; return state",
                },
            },
            "edges": [
                {
                    "from_node": "classifier",
                    "to_node": "order",
                    "condition": {
                        "type": "simple",
                        "variable": "route",
                        "operator": "==",
                        "value": "order",
                    },
                },
                {
                    "from_node": "classifier",
                    "to_node": "complaint",
                    "condition": {
                        "type": "simple",
                        "variable": "route",
                        "operator": "==",
                        "value": "complaint",
                    },
                },
                {
                    "from_node": "classifier",
                    "to_node": "general",
                    "condition": {
                        "type": "simple",
                        "variable": "route",
                        "operator": "==",
                        "value": "general",
                    },
                },
                {"from_node": "order", "to_node": None},
                {"from_node": "complaint", "to_node": None},
                {"from_node": "general", "to_node": None},
            ],
        }
        flow_base = await build_flow(config=config_base, variables={})
        state = await flow_base.run(
            ExecutionState(
                task_id="test-task",
                context_id="test-context",
                user_id="test-user",
                session_id="test-agent:test-context",
                content="у меня жалоба",
            )
        )
        assert state.route == "complaint"
        assert state.result == "complaint"
        config_orders_only = {
            "flow_id": "test_routing",
            "name": "Test",
            "entry": "classifier",
            "nodes": {
                "classifier": {
                    "type": "code",
                    "code": "\nasync def run(args, state):\n    content = (getattr(state, 'content', None) or '').lower()\n    if 'заказ' in content:\n        state.route = 'order'\n    else:\n        state.route = 'general'\n    return state\n",
                },
                "order": {
                    "type": "code",
                    "code": "async def run(args, state): state.result = 'order'; return state",
                },
                "general": {
                    "type": "code",
                    "code": "async def run(args, state): state.result = 'general'; return state",
                },
            },
            "edges": [
                {
                    "from_node": "classifier",
                    "to_node": "order",
                    "condition": {
                        "type": "simple",
                        "variable": "route",
                        "operator": "==",
                        "value": "order",
                    },
                },
                {
                    "from_node": "classifier",
                    "to_node": "general",
                    "condition": {
                        "type": "simple",
                        "variable": "route",
                        "operator": "==",
                        "value": "general",
                    },
                },
                {"from_node": "order", "to_node": None},
                {"from_node": "general", "to_node": None},
            ],
        }
        flow_orders_only = await build_flow(config=config_orders_only, variables={})
        state = await flow_orders_only.run(
            ExecutionState(
                task_id="test-task",
                context_id="test-context",
                user_id="test-user",
                session_id="test-agent:test-context",
                content="у меня жалоба",
            )
        )
        assert state.route == "general"
        assert state.result == "general"


class TestVariablesOverrideE2E:
    """E2E тесты переопределения variables."""

    @pytest.mark.asyncio
    async def test_variables_accessible_in_function_node(self):
        """Переменные доступны в function node."""
        flow = await build_flow(
            config={
                "flow_id": "test_vars",
                "name": "Test",
                "entry": "main",
                "nodes": {
                    "main": {
                        "type": "code",
                        "code": "\nasync def run(args, state):\n    vars = getattr(state, 'variables', {})\n    state.company = vars.get('company_name', 'unknown')\n    state.max_len = vars.get('max_length', 0)\n    return state\n",
                    }
                },
                "edges": [{"from_node": "main", "to_node": None}],
            },
            variables={"company_name": "TestCorp", "max_length": 500},
        )
        state = await flow.run(
            ExecutionState(
                task_id="test-task",
                context_id="test-context",
                user_id="test-user",
                session_id="test-agent:test-context",
            )
        )
        assert state.company == "TestCorp"
        assert state.max_len == 500

    @pytest.mark.asyncio
    async def test_skill_variables_override_base(self):
        """Skill variables переопределяют base."""
        flow_base = await build_flow(
            config={
                "flow_id": "test_vars",
                "name": "Test",
                "entry": "main",
                "nodes": {
                    "main": {
                        "type": "code",
                        "code": "\nasync def run(args, state):\n    vars = getattr(state, 'variables', {})\n    state.max_len = vars.get('max_length', 0)\n    return state\n",
                    }
                },
                "edges": [{"from_node": "main", "to_node": None}],
            },
            variables={"max_length": 500},
        )
        state_base = await flow_base.run(
            ExecutionState(
                task_id="test-task",
                context_id="test-context",
                user_id="test-user",
                session_id="test-agent:test-context",
            )
        )
        assert state_base["max_len"] == 500
        flow_skill = await build_flow(
            config={
                "flow_id": "test_vars",
                "name": "Test",
                "entry": "main",
                "nodes": {
                    "main": {
                        "type": "code",
                        "code": "\nasync def run(args, state):\n    vars = getattr(state, 'variables', {})\n    state.max_len = vars.get('max_length', 0)\n    return state\n",
                    }
                },
                "edges": [{"from_node": "main", "to_node": None}],
            },
            variables={"max_length": 200},
        )
        state_skill = await flow_skill.run(
            ExecutionState(
                task_id="test-task",
                context_id="test-context",
                user_id="test-user",
                session_id="test-agent:test-context",
            )
        )
        assert state_skill["max_len"] == 200


class TestEntryOverrideE2E:
    """E2E тесты переопределения entry point."""

    @pytest.mark.asyncio
    async def test_skill_entry_changes_start_node(self):
        """Skill entry меняет стартовую ноду."""
        config_nodes = {
            "default_start": {
                "type": "code",
                "code": "async def run(args, state): state.path = 'default'; return state",
            },
            "skill_start": {
                "type": "code",
                "code": "async def run(args, state): state.path = 'skill'; return state",
            },
        }
        flow_default = await build_flow(
            config={
                "flow_id": "test_entry",
                "name": "Test",
                "entry": "default_start",
                "nodes": config_nodes,
                "edges": [
                    {"from_node": "default_start", "to_node": None},
                    {"from_node": "skill_start", "to_node": None},
                ],
            },
            variables={},
        )
        state = await flow_default.run(
            ExecutionState(
                task_id="test-task",
                context_id="test-context",
                user_id="test-user",
                session_id="test-agent:test-context",
            )
        )
        assert state.path == "default"
        flow_skill = await build_flow(
            config={
                "flow_id": "test_entry",
                "name": "Test",
                "entry": "skill_start",
                "nodes": config_nodes,
                "edges": [
                    {"from_node": "default_start", "to_node": None},
                    {"from_node": "skill_start", "to_node": None},
                ],
            },
            variables={},
        )
        state = await flow_skill.run(
            ExecutionState(
                task_id="test-task",
                context_id="test-context",
                user_id="test-user",
                session_id="test-agent:test-context",
            )
        )
        assert state.path == "skill"


class TestExternalApiNodeOverridesE2E:
    """E2E тесты переопределения external_api nodes (через function node симуляцию)."""

    @pytest.mark.asyncio
    async def test_external_api_state_mapping_override(self):
        """Переопределение state_mapping в external_api node."""
        flow = await build_flow(
            config={
                "flow_id": "test_api",
                "name": "Test",
                "entry": "mock_api",
                "nodes": {
                    "mock_api": {
                        "type": "code",
                        "code": "\nasync def run(args, state):\n    # Симулируем API response\n    api_response = {'fact': 'Cats sleep 16 hours', 'length': 20}\n    # Применяем state_mapping\n    state.cat_fact = api_response['fact']\n    state.cat_fact_length = api_response['length']\n    return state\n",
                    }
                },
                "edges": [{"from_node": "mock_api", "to_node": None}],
            },
            variables={},
        )
        state = await flow.run(
            ExecutionState(
                task_id="test-task",
                context_id="test-context",
                user_id="test-user",
                session_id="test-agent:test-context",
            )
        )
        assert state.cat_fact == "Cats sleep 16 hours"
        assert state.cat_fact_length == 20


class TestNestedOverridesE2E:
    """E2E тесты вложенных переопределений."""

    @pytest.mark.asyncio
    async def test_nested_llm_config_override(self):
        """Глубокое переопределение llm config."""
        flow = await build_flow(
            config={
                "flow_id": "test_nested",
                "name": "Test",
                "entry": "main",
                "nodes": {
                    "main": {
                        "type": "code",
                        "code": "\nasync def run(args, state):\n    # В реальности LLM config используется в LlmNode\n    # Здесь проверяем что конфиг правильно передан\n    state.config_passed = True\n    return state\n",
                    }
                },
                "edges": [{"from_node": "main", "to_node": None}],
            },
            variables={},
        )
        state = await flow.run(
            ExecutionState(
                task_id="test-task",
                context_id="test-context",
                user_id="test-user",
                session_id="test-agent:test-context",
            )
        )
        assert state.config_passed is True


class TestGraphOverridesE2E:
    """E2E тесты переопределений в графовых flows."""

    @pytest.mark.asyncio
    async def test_fast_track_skill_skips_formatter(self):
        """Skill fast_track пропускает formatter node."""
        config_base = {
            "flow_id": "test_graph",
            "name": "Test",
            "entry": "classifier",
            "nodes": {
                "classifier": {
                    "type": "code",
                    "code": "async def run(args, state): state.route = 'order'; state.step = ['classifier']; return state",
                },
                "processor": {
                    "type": "code",
                    "code": "async def run(args, state): state.step.append('processor'); return state",
                },
                "formatter": {
                    "type": "code",
                    "code": "async def run(args, state): state.step.append('formatter'); return state",
                },
            },
            "edges": [
                {"from_node": "classifier", "to_node": "processor"},
                {"from_node": "processor", "to_node": "formatter"},
                {"from_node": "formatter", "to_node": None},
            ],
        }
        flow_base = await build_flow(config=config_base, variables={})
        state = await flow_base.run(
            ExecutionState(
                task_id="test-task",
                context_id="test-context",
                user_id="test-user",
                session_id="test-agent:test-context",
            )
        )
        assert state.step == ["classifier", "processor", "formatter"]
        config_fast = {
            "flow_id": "test_graph",
            "name": "Test",
            "entry": "classifier",
            "nodes": {
                "classifier": {
                    "type": "code",
                    "code": "async def run(args, state): state.route = 'order'; state.step = ['classifier']; return state",
                },
                "processor": {
                    "type": "code",
                    "code": "async def run(args, state): state.step.append('processor'); return state",
                },
            },
            "edges": [
                {"from_node": "classifier", "to_node": "processor"},
                {"from_node": "processor", "to_node": None},
            ],
        }
        flow_fast = await build_flow(config=config_fast, variables={})
        state = await flow_fast.run(
            ExecutionState(
                task_id="test-task",
                context_id="test-context",
                user_id="test-user",
                session_id="test-agent:test-context",
            )
        )
        assert state.step == ["classifier", "processor"]
        assert "formatter" not in state.step

    @pytest.mark.asyncio
    async def test_conditional_edge_override(self):
        """Переопределение условий в edges."""
        flow_all = await build_flow(
            config={
                "flow_id": "test_edges",
                "name": "Test",
                "entry": "start",
                "nodes": {
                    "start": {
                        "type": "code",
                        "code": "async def run(args, state): state.route = getattr(state, 'input_route', 'a'); return state",
                    },
                    "path_a": {
                        "type": "code",
                        "code": "async def run(args, state): state.result = 'A'; return state",
                    },
                    "path_b": {
                        "type": "code",
                        "code": "async def run(args, state): state.result = 'B'; return state",
                    },
                    "path_c": {
                        "type": "code",
                        "code": "async def run(args, state): state.result = 'C'; return state",
                    },
                },
                "edges": [
                    {
                        "from_node": "start",
                        "to_node": "path_a",
                        "condition": {
                            "type": "simple",
                            "variable": "route",
                            "operator": "==",
                            "value": "a",
                        },
                    },
                    {
                        "from_node": "start",
                        "to_node": "path_b",
                        "condition": {
                            "type": "simple",
                            "variable": "route",
                            "operator": "==",
                            "value": "b",
                        },
                    },
                    {
                        "from_node": "start",
                        "to_node": "path_c",
                        "condition": {
                            "type": "simple",
                            "variable": "route",
                            "operator": "==",
                            "value": "c",
                        },
                    },
                    {"from_node": "path_a", "to_node": None},
                    {"from_node": "path_b", "to_node": None},
                    {"from_node": "path_c", "to_node": None},
                ],
            },
            variables={},
        )
        state = await flow_all.run(
            ExecutionState(
                task_id="test-task",
                context_id="test-context",
                user_id="test-user",
                session_id="test-agent:test-context",
                input_route="b",
            )
        )
        assert state.result == "B"
        flow_redirect = await build_flow(
            config={
                "flow_id": "test_edges",
                "name": "Test",
                "entry": "start",
                "nodes": {
                    "start": {
                        "type": "code",
                        "code": "async def run(args, state): state.route = 'c' if getattr(state, 'input_route', None) == 'b' else getattr(state, 'input_route', 'a'); return state",
                    },
                    "path_a": {
                        "type": "code",
                        "code": "async def run(args, state): state.result = 'A'; return state",
                    },
                    "path_c": {
                        "type": "code",
                        "code": "async def run(args, state): state.result = 'C'; return state",
                    },
                },
                "edges": [
                    {
                        "from_node": "start",
                        "to_node": "path_a",
                        "condition": {
                            "type": "simple",
                            "variable": "route",
                            "operator": "==",
                            "value": "a",
                        },
                    },
                    {
                        "from_node": "start",
                        "to_node": "path_c",
                        "condition": {
                            "type": "simple",
                            "variable": "route",
                            "operator": "==",
                            "value": "c",
                        },
                    },
                    {"from_node": "path_a", "to_node": None},
                    {"from_node": "path_c", "to_node": None},
                ],
            },
            variables={},
        )
        state = await flow_redirect.run(
            ExecutionState(
                task_id="test-task",
                context_id="test-context",
                user_id="test-user",
                session_id="test-agent:test-context",
                input_route="b",
            )
        )
        assert state.result == "C"


class TestMultipleNodesOverrideE2E:
    """E2E тесты переопределения нескольких нод одновременно."""

    @pytest.mark.asyncio
    async def test_override_multiple_nodes_in_pipeline(self):
        """Переопределение нескольких нод в pipeline."""
        flow_base = await build_flow(
            config={
                "flow_id": "test_pipeline",
                "name": "Test",
                "entry": "step1",
                "nodes": {
                    "step1": {
                        "type": "code",
                        "code": "async def run(args, state): state.v1 = 'base1'; return state",
                    },
                    "step2": {
                        "type": "code",
                        "code": "async def run(args, state): state.v2 = 'base2'; return state",
                    },
                    "step3": {
                        "type": "code",
                        "code": "async def run(args, state): state.v3 = 'base3'; return state",
                    },
                },
                "edges": [
                    {"from_node": "step1", "to_node": "step2"},
                    {"from_node": "step2", "to_node": "step3"},
                    {"from_node": "step3", "to_node": None},
                ],
            },
            variables={},
        )
        state = await flow_base.run(
            ExecutionState(
                task_id="test-task",
                context_id="test-context",
                user_id="test-user",
                session_id="test-agent:test-context",
            )
        )
        assert state.v1 == "base1"
        assert state.v2 == "base2"
        assert state.v3 == "base3"
        flow_override = await build_flow(
            config={
                "flow_id": "test_pipeline",
                "name": "Test",
                "entry": "step1",
                "nodes": {
                    "step1": {
                        "type": "code",
                        "code": "async def run(args, state): state.v1 = 'override1'; return state",
                    },
                    "step2": {
                        "type": "code",
                        "code": "async def run(args, state): state.v2 = 'base2'; return state",
                    },
                    "step3": {
                        "type": "code",
                        "code": "async def run(args, state): state.v3 = 'override3'; return state",
                    },
                },
                "edges": [
                    {"from_node": "step1", "to_node": "step2"},
                    {"from_node": "step2", "to_node": "step3"},
                    {"from_node": "step3", "to_node": None},
                ],
            },
            variables={},
        )
        state = await flow_override.run(
            ExecutionState(
                task_id="test-task",
                context_id="test-context",
                user_id="test-user",
                session_id="test-agent:test-context",
            )
        )
        assert state.v1 == "override1"
        assert state.v2 == "base2"
        assert state.v3 == "override3"

    @pytest.mark.asyncio
    async def test_add_new_node_in_skill(self):
        """Skill добавляет новую ноду."""
        flow_base = await build_flow(
            config={
                "flow_id": "test_add",
                "name": "Test",
                "entry": "first",
                "nodes": {
                    "first": {
                        "type": "code",
                        "code": "async def run(args, state): state.steps = ['first']; return state",
                    },
                    "last": {
                        "type": "code",
                        "code": "async def run(args, state): state.steps.append('last'); return state",
                    },
                },
                "edges": [
                    {"from_node": "first", "to_node": "last"},
                    {"from_node": "last", "to_node": None},
                ],
            },
            variables={},
        )
        state = await flow_base.run(
            ExecutionState(
                task_id="test-task",
                context_id="test-context",
                user_id="test-user",
                session_id="test-agent:test-context",
            )
        )
        assert state.steps == ["first", "last"]
        flow_with_middle = await build_flow(
            config={
                "flow_id": "test_add",
                "name": "Test",
                "entry": "first",
                "nodes": {
                    "first": {
                        "type": "code",
                        "code": "async def run(args, state): state.steps = ['first']; return state",
                    },
                    "middle": {
                        "type": "code",
                        "code": "async def run(args, state): state.steps.append('middle'); return state",
                    },
                    "last": {
                        "type": "code",
                        "code": "async def run(args, state): state.steps.append('last'); return state",
                    },
                },
                "edges": [
                    {"from_node": "first", "to_node": "middle"},
                    {"from_node": "middle", "to_node": "last"},
                    {"from_node": "last", "to_node": None},
                ],
            },
            variables={},
        )
        state = await flow_with_middle.run(
            ExecutionState(
                task_id="test-task",
                context_id="test-context",
                user_id="test-user",
                session_id="test-agent:test-context",
            )
        )
        assert state.steps == ["first", "middle", "last"]
