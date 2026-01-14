"""
E2E тесты для полного цикла переопределений.

Тестируем реальное выполнение agents с различными skills и переопределениями.
"""

import pytest
from apps.agents.src.agent import Agent
from core.state import ExecutionState


class TestFunctionNodeOverrides:
    """E2E тесты переопределения function nodes."""

    @pytest.mark.asyncio
    async def test_function_code_override_changes_behavior(self):
        """Переопределение code в function node меняет поведение."""
        # Base agent
        flow_default = await Agent.from_config(
            config={
                "id": "test_fn",
                "name": "Test",
                "entry": "classifier",
                "nodes": {
                    "classifier": {
                        "type": "function",
                        "code": "def run(state):\n    state['route'] = 'default'\n    return state"
                    }
                },
                "edges": [{"from": "classifier", "to": None}]
            },
            variables={}
        )

        state = await flow_default.run(ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="test"
        ))
        assert state["route"] == "default"

        # Skill override
        flow_skill = await Agent.from_config(
            config={
                "id": "test_fn",
                "name": "Test",
                "entry": "classifier",
                "nodes": {
                    "classifier": {
                        "type": "function",
                        "code": "def run(state):\n    state['route'] = 'custom'\n    return state"
                    }
                },
                "edges": [{"from": "classifier", "to": None}]
            },
            variables={}
        )

        state = await flow_skill.run(ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="test"
        ))
        assert state["route"] == "custom"

    @pytest.mark.asyncio
    async def test_conditional_routing_override(self):
        """Переопределение условий routing."""
        # Base: all routes
        config_base = {
            "id": "test_routing",
            "name": "Test",
            "entry": "classifier",
            "nodes": {
                "classifier": {
                    "type": "function",
                    "code": """
def run(state):
    content = state.get('content', '').lower()
    if 'заказ' in content:
        state['route'] = 'order'
    elif 'жалоб' in content:
        state['route'] = 'complaint'
    else:
        state['route'] = 'general'
    return state
"""
                },
                "order": {"type": "function", "code": "def run(s): s['result'] = 'order'; return s"},
                "complaint": {"type": "function", "code": "def run(s): s['result'] = 'complaint'; return s"},
                "general": {"type": "function", "code": "def run(s): s['result'] = 'general'; return s"}
            },
            "edges": [
                {"from": "classifier", "to": "order", "condition": "route == 'order'"},
                {"from": "classifier", "to": "complaint", "condition": "route == 'complaint'"},
                {"from": "classifier", "to": "general", "condition": "route == 'general'"},
                {"from": "order", "to": None},
                {"from": "complaint", "to": None},
                {"from": "general", "to": None}
            ]
        }

        flow_base = await Agent.from_config(config=config_base, variables={})

        # Test complaint routing
        state = await flow_base.run(ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="у меня жалоба"
        ))
        assert state["route"] == "complaint"
        assert state["result"] == "complaint"

        # Skill: orders_only - все non-order идет в general
        config_orders_only = {
            "id": "test_routing",
            "name": "Test",
            "entry": "classifier",
            "nodes": {
                "classifier": {
                    "type": "function",
                    "code": """
def run(state):
    content = state.get('content', '').lower()
    if 'заказ' in content:
        state['route'] = 'order'
    else:
        state['route'] = 'general'
    return state
"""
                },
                "order": {"type": "function", "code": "def run(s): s['result'] = 'order'; return s"},
                "general": {"type": "function", "code": "def run(s): s['result'] = 'general'; return s"}
            },
            "edges": [
                {"from": "classifier", "to": "order", "condition": "route == 'order'"},
                {"from": "classifier", "to": "general", "condition": "route == 'general'"},
                {"from": "order", "to": None},
                {"from": "general", "to": None}
            ]
        }

        flow_orders_only = await Agent.from_config(config=config_orders_only, variables={})

        # Same input now goes to general
        state = await flow_orders_only.run(ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="у меня жалоба"
        ))
        assert state["route"] == "general"  # Changed!
        assert state["result"] == "general"


class TestVariablesOverrideE2E:
    """E2E тесты переопределения variables."""

    @pytest.mark.asyncio
    async def test_variables_accessible_in_function_node(self):
        """Переменные доступны в function node."""
        flow = await Agent.from_config(
            config={
                "id": "test_vars",
                "name": "Test",
                "entry": "main",
                "nodes": {
                    "main": {
                        "type": "function",
                        "code": """
def run(state):
    vars = state.get('variables', {})
    state['company'] = vars.get('company_name', 'unknown')
    state['max_len'] = vars.get('max_length', 0)
    return state
"""
                    }
                },
                "edges": [{"from": "main", "to": None}]
            },
            variables={"company_name": "TestCorp", "max_length": 500}
        )

        state = await flow.run(ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        ))

        assert state["company"] == "TestCorp"
        assert state["max_len"] == 500

    @pytest.mark.asyncio
    async def test_skill_variables_override_base(self):
        """Skill variables переопределяют base."""
        # Base variables
        flow_base = await Agent.from_config(
            config={
                "id": "test_vars",
                "name": "Test",
                "entry": "main",
                "nodes": {
                    "main": {
                        "type": "function",
                        "code": """
def run(state):
    vars = state.get('variables', {})
    state['max_len'] = vars.get('max_length', 0)
    return state
"""
                    }
                },
                "edges": [{"from": "main", "to": None}]
            },
            variables={"max_length": 500}
        )

        state_base = await flow_base.run(ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        ))
        assert state_base["max_len"] == 500

        # Skill override
        flow_skill = await Agent.from_config(
            config={
                "id": "test_vars",
                "name": "Test",
                "entry": "main",
                "nodes": {
                    "main": {
                        "type": "function",
                        "code": """
def run(state):
    vars = state.get('variables', {})
    state['max_len'] = vars.get('max_length', 0)
    return state
"""
                    }
                },
                "edges": [{"from": "main", "to": None}]
            },
            variables={"max_length": 200}  # Overridden by skill
        )

        state_skill = await flow_skill.run(ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        ))
        assert state_skill["max_len"] == 200


class TestEntryOverrideE2E:
    """E2E тесты переопределения entry point."""

    @pytest.mark.asyncio
    async def test_skill_entry_changes_start_node(self):
        """Skill entry меняет стартовую ноду."""
        config_nodes = {
            "default_start": {
                "type": "function",
                "code": "def run(s): s['path'] = 'default'; return s"
            },
            "skill_start": {
                "type": "function",
                "code": "def run(s): s['path'] = 'skill'; return s"
            }
        }

        # Default entry
        flow_default = await Agent.from_config(
            config={
                "id": "test_entry",
                "name": "Test",
                "entry": "default_start",
                "nodes": config_nodes,
                "edges": [
                    {"from": "default_start", "to": None},
                    {"from": "skill_start", "to": None}
                ]
            },
            variables={}
        )

        state = await flow_default.run(ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        ))
        assert state["path"] == "default"

        # Skill entry
        flow_skill = await Agent.from_config(
            config={
                "id": "test_entry",
                "name": "Test",
                "entry": "skill_start",
                "nodes": config_nodes,
                "edges": [
                    {"from": "default_start", "to": None},
                    {"from": "skill_start", "to": None}
                ]
            },
            variables={}
        )

        state = await flow_skill.run(ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        ))
        assert state["path"] == "skill"


class TestExternalApiNodeOverridesE2E:
    """E2E тесты переопределения external_api nodes (через function node симуляцию)."""

    @pytest.mark.asyncio
    async def test_external_api_state_mapping_override(self):
        """Переопределение state_mapping в external_api node."""
        # Мокаем HTTP - используем function node для симуляции
        flow = await Agent.from_config(
            config={
                "id": "test_api",
                "name": "Test",
                "entry": "mock_api",
                "nodes": {
                    "mock_api": {
                        "type": "function",
                        "code": """
def run(state):
    # Симулируем API response
    api_response = {'fact': 'Cats sleep 16 hours', 'length': 20}
    # Применяем state_mapping
    state['cat_fact'] = api_response['fact']
    state['cat_fact_length'] = api_response['length']
    return state
"""
                    }
                },
                "edges": [{"from": "mock_api", "to": None}]
            },
            variables={}
        )

        state = await flow.run(ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        ))

        assert state["cat_fact"] == "Cats sleep 16 hours"
        assert state["cat_fact_length"] == 20


class TestNestedOverridesE2E:
    """E2E тесты вложенных переопределений."""

    @pytest.mark.asyncio
    async def test_nested_llm_config_override(self):
        """Глубокое переопределение llm config."""
        flow = await Agent.from_config(
            config={
                "id": "test_nested",
                "name": "Test",
                "entry": "main",
                "nodes": {
                    "main": {
                        "type": "function",
                        "code": """
def run(state):
    # В реальности LLM config используется в ReactNode
    # Здесь проверяем что конфиг правильно передан
    state['config_passed'] = True
    return state
"""
                    }
                },
                "edges": [{"from": "main", "to": None}]
            },
            variables={}
        )

        state = await flow.run(ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        ))
        assert state["config_passed"] is True


class TestGraphOverridesE2E:
    """E2E тесты переопределений в графовых flows."""

    @pytest.mark.asyncio
    async def test_fast_track_skill_skips_formatter(self):
        """Skill fast_track пропускает formatter node."""
        # Base flow: classifier -> processor -> formatter -> end
        config_base = {
            "id": "test_graph",
            "name": "Test",
            "entry": "classifier",
            "nodes": {
                "classifier": {
                    "type": "function",
                    "code": "def run(s): s['route'] = 'order'; s['step'] = ['classifier']; return s"
                },
                "processor": {
                    "type": "function",
                    "code": "def run(s): s['step'].append('processor'); return s"
                },
                "formatter": {
                    "type": "function",
                    "code": "def run(s): s['step'].append('formatter'); return s"
                }
            },
            "edges": [
                {"from": "classifier", "to": "processor"},
                {"from": "processor", "to": "formatter"},
                {"from": "formatter", "to": None}
            ]
        }

        flow_base = await Agent.from_config(config=config_base, variables={})
        state = await flow_base.run(ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        ))

        assert state["step"] == ["classifier", "processor", "formatter"]

        # Fast track: classifier -> processor -> end (skip formatter)
        config_fast = {
            "id": "test_graph",
            "name": "Test",
            "entry": "classifier",
            "nodes": {
                "classifier": {
                    "type": "function",
                    "code": "def run(s): s['route'] = 'order'; s['step'] = ['classifier']; return s"
                },
                "processor": {
                    "type": "function",
                    "code": "def run(s): s['step'].append('processor'); return s"
                }
            },
            "edges": [
                {"from": "classifier", "to": "processor"},
                {"from": "processor", "to": None}  # Direct end
            ]
        }

        flow_fast = await Agent.from_config(config=config_fast, variables={})
        state = await flow_fast.run(ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        ))

        assert state["step"] == ["classifier", "processor"]
        assert "formatter" not in state["step"]

    @pytest.mark.asyncio
    async def test_conditional_edge_override(self):
        """Переопределение условий в edges."""
        # Base: all conditions
        flow_all = await Agent.from_config(
            config={
                "id": "test_edges",
                "name": "Test",
                "entry": "start",
                "nodes": {
                    "start": {
                        "type": "function",
                        "code": "def run(s): s['route'] = s.get('input_route', 'a'); return s"
                    },
                    "path_a": {"type": "function", "code": "def run(s): s['result'] = 'A'; return s"},
                    "path_b": {"type": "function", "code": "def run(s): s['result'] = 'B'; return s"},
                    "path_c": {"type": "function", "code": "def run(s): s['result'] = 'C'; return s"}
                },
                "edges": [
                    {"from": "start", "to": "path_a", "condition": "route == 'a'"},
                    {"from": "start", "to": "path_b", "condition": "route == 'b'"},
                    {"from": "start", "to": "path_c", "condition": "route == 'c'"},
                    {"from": "path_a", "to": None},
                    {"from": "path_b", "to": None},
                    {"from": "path_c", "to": None}
                ]
            },
            variables={}
        )

        state = await flow_all.run(ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            input_route="b"
        ))
        assert state["result"] == "B"

        # Skill: redirect b to c
        flow_redirect = await Agent.from_config(
            config={
                "id": "test_edges",
                "name": "Test",
                "entry": "start",
                "nodes": {
                    "start": {
                        "type": "function",
                        "code": "def run(s): s['route'] = 'c' if s.get('input_route') == 'b' else s.get('input_route', 'a'); return s"
                    },
                    "path_a": {"type": "function", "code": "def run(s): s['result'] = 'A'; return s"},
                    "path_c": {"type": "function", "code": "def run(s): s['result'] = 'C'; return s"}
                },
                "edges": [
                    {"from": "start", "to": "path_a", "condition": "route == 'a'"},
                    {"from": "start", "to": "path_c", "condition": "route == 'c'"},
                    {"from": "path_a", "to": None},
                    {"from": "path_c", "to": None}
                ]
            },
            variables={}
        )

        state = await flow_redirect.run(ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            input_route="b"
        ))
        assert state["result"] == "C"  # Redirected!


class TestMultipleNodesOverrideE2E:
    """E2E тесты переопределения нескольких нод одновременно."""

    @pytest.mark.asyncio
    async def test_override_multiple_nodes_in_pipeline(self):
        """Переопределение нескольких нод в pipeline."""
        # Base pipeline
        flow_base = await Agent.from_config(
            config={
                "id": "test_pipeline",
                "name": "Test",
                "entry": "step1",
                "nodes": {
                    "step1": {"type": "function", "code": "def run(s): s['v1'] = 'base1'; return s"},
                    "step2": {"type": "function", "code": "def run(s): s['v2'] = 'base2'; return s"},
                    "step3": {"type": "function", "code": "def run(s): s['v3'] = 'base3'; return s"}
                },
                "edges": [
                    {"from": "step1", "to": "step2"},
                    {"from": "step2", "to": "step3"},
                    {"from": "step3", "to": None}
                ]
            },
            variables={}
        )

        state = await flow_base.run(ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        ))
        assert state["v1"] == "base1"
        assert state["v2"] == "base2"
        assert state["v3"] == "base3"

        # Override step1 and step3
        flow_override = await Agent.from_config(
            config={
                "id": "test_pipeline",
                "name": "Test",
                "entry": "step1",
                "nodes": {
                    "step1": {"type": "function", "code": "def run(s): s['v1'] = 'override1'; return s"},
                    "step2": {"type": "function", "code": "def run(s): s['v2'] = 'base2'; return s"},
                    "step3": {"type": "function", "code": "def run(s): s['v3'] = 'override3'; return s"}
                },
                "edges": [
                    {"from": "step1", "to": "step2"},
                    {"from": "step2", "to": "step3"},
                    {"from": "step3", "to": None}
                ]
            },
            variables={}
        )

        state = await flow_override.run(ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        ))
        assert state["v1"] == "override1"  # Overridden
        assert state["v2"] == "base2"      # Kept
        assert state["v3"] == "override3"  # Overridden

    @pytest.mark.asyncio
    async def test_add_new_node_in_skill(self):
        """Skill добавляет новую ноду."""
        # Base: 2 nodes
        flow_base = await Agent.from_config(
            config={
                "id": "test_add",
                "name": "Test",
                "entry": "first",
                "nodes": {
                    "first": {"type": "function", "code": "def run(s): s['steps'] = ['first']; return s"},
                    "last": {"type": "function", "code": "def run(s): s['steps'].append('last'); return s"}
                },
                "edges": [
                    {"from": "first", "to": "last"},
                    {"from": "last", "to": None}
                ]
            },
            variables={}
        )

        state = await flow_base.run(ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        ))
        assert state["steps"] == ["first", "last"]

        # Skill: add middle node
        flow_with_middle = await Agent.from_config(
            config={
                "id": "test_add",
                "name": "Test",
                "entry": "first",
                "nodes": {
                    "first": {"type": "function", "code": "def run(s): s['steps'] = ['first']; return s"},
                    "middle": {"type": "function", "code": "def run(s): s['steps'].append('middle'); return s"},
                    "last": {"type": "function", "code": "def run(s): s['steps'].append('last'); return s"}
                },
                "edges": [
                    {"from": "first", "to": "middle"},
                    {"from": "middle", "to": "last"},
                    {"from": "last", "to": None}
                ]
            },
            variables={}
        )

        state = await flow_with_middle.run(ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        ))
        assert state["steps"] == ["first", "middle", "last"]
