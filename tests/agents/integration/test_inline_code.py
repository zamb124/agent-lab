"""
Интеграционные тесты для INLINE_CODE.
"""

import pytest
from apps.agents.src.agent import Agent
from apps.agents.src.agent.nodes import create_node, FunctionNode, FunctionNode
from apps.agents.src.models import AgentConfig, Edge, CodeMode, ToolReference
from apps.agents.src.tools import InlineTool
from apps.agents.src.eval import SafeEvalError
from core.state import ExecutionState


class TestFunctionNode:
    """Тесты FunctionNode."""

    @pytest.mark.asyncio
    async def test_create_inline_node(self):
        """Создание inline ноды."""
        node_config = {
            "type": "function",
            "code": """
def run(state):
    state['result'] = 'inline_ok'
    return state
"""
        }
        node = await create_node("test_inline", node_config)
        
        assert isinstance(node, FunctionNode)
        assert node.node_id == "test_inline"

    @pytest.mark.asyncio
    async def test_create_reference_node(self):
        """Создание reference ноды (без code)."""
        node_config = {
            "type": "function",
            "function": "json.loads"
        }
        node = await create_node("test_ref", node_config)
        
        assert isinstance(node, FunctionNode)
        assert node.node_id == "test_ref"

    @pytest.mark.asyncio
    async def test_inline_node_execution(self):
        """Выполнение inline ноды."""
        code = """
async def run(state):
    state['doubled'] = state.get('value', 0) * 2
    return state
"""
        node = FunctionNode(node_id="doubler", code=code)
        
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            value=21
        )
        result = await node.run(state)
        
        assert result["doubled"] == 42

    @pytest.mark.asyncio
    async def test_inline_node_with_variables(self):
        """Доступ к variables из inline кода."""
        code = """
def run(state):
    vars = state.get('variables', {})
    state['greeting'] = f"Hello, {vars.get('company', 'World')}!"
    return state
"""
        node = FunctionNode(node_id="greeter", code=code)
        
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            variables={"company": "Platform"}
        )
        result = await node.run(state)
        
        assert result["greeting"] == "Hello, Platform!"

    @pytest.mark.asyncio
    async def test_inline_node_blocked_import(self):
        """Блокировка опасного импорта в inline ноде."""
        code = """
import os

def run(state):
    state['files'] = os.listdir('/')
    return state
"""
        node = FunctionNode(node_id="bad_node", code=code)
        
        with pytest.raises(SafeEvalError, match="Import of 'os' is not allowed"):
            await node.run(ExecutionState(
                task_id="test-task",
                context_id="test-context",
                user_id="test-user",
                session_id="test-agent:test-context",
            ))


class TestFlowWithInlineCode:
    """Тесты Agent с inline кодом."""

    @pytest.mark.asyncio
    async def test_flow_with_single_inline_node(self):
        """Agent с одной inline нодой."""
        config = AgentConfig(
            agent_id="inline_test",
            name="Inline Test",
            entry="process",
            nodes={
                "process": {
                    "type": "function",
                    "code": """
def run(state):
    state['processed'] = True
    state['value'] = state.get('input', 0) + 100
    return state
"""
                }
            },
            edges=[
                Edge(from_node="process", to_node=None)
            ]
        )
        
        flow = await Agent.from_config(
            config={
                "id": config.agent_id,
                "name": config.name,
                "entry": config.entry,
                "nodes": config.nodes,
                "edges": config.edges
            },
            variables={}
        )
        
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            input=42
        )
        result = await flow.run(state)
        
        assert result["processed"] is True
        assert result["value"] == 142

    @pytest.mark.asyncio
    async def test_flow_with_multiple_inline_nodes(self):
        """Agent с несколькими inline нодами."""
        config = AgentConfig(
            agent_id="multi_inline",
            name="Multi Inline",
            entry="step1",
            nodes={
                "step1": {
                    "type": "function",
                    "code": """
def run(state):
    state['step1'] = 'done'
    state['counter'] = 1
    return state
"""
                },
                "step2": {
                    "type": "function",
                    "code": """
def run(state):
    state['step2'] = 'done'
    state['counter'] = state.get('counter', 0) + 1
    return state
"""
                },
                "step3": {
                    "type": "function",
                    "code": """
def run(state):
    state['step3'] = 'done'
    state['counter'] = state.get('counter', 0) + 1
    return state
"""
                }
            },
            edges=[
                Edge(from_node="step1", to_node="step2"),
                Edge(from_node="step2", to_node="step3"),
                Edge(from_node="step3", to_node=None)
            ]
        )
        
        flow = await Agent.from_config(
            config={
                "id": config.agent_id,
                "name": config.name,
                "entry": config.entry,
                "nodes": config.nodes,
                "edges": config.edges
            },
            variables={}
        )
        
        from core.state import ExecutionState
        result = await flow.run(ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        ))
        
        assert result["step1"] == "done"
        assert result["step2"] == "done"
        assert result["step3"] == "done"
        assert result["counter"] == 3

    @pytest.mark.asyncio
    async def test_flow_inline_with_json(self):
        """Agent с inline кодом использующим json."""
        config = AgentConfig(
            agent_id="json_inline",
            name="JSON Inline",
            entry="parse",
            nodes={
                "parse": {
                    "type": "function",
                    "code": """
import json

def run(state):
    data = json.loads(state.get('json_input', '{}'))
    state['parsed'] = data
    state['name'] = data.get('name', 'unknown')
    return state
"""
                }
            },
            edges=[
                Edge(from_node="parse", to_node=None)
            ]
        )
        
        flow = await Agent.from_config(
            config={
                "id": config.agent_id,
                "name": config.name,
                "entry": config.entry,
                "nodes": config.nodes,
                "edges": config.edges
            },
            variables={}
        )
        
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            json_input='{"name": "Test", "value": 123}'
        )
        result = await flow.run(state)
        
        assert result["name"] == "Test"
        assert result["parsed"]["value"] == 123

    @pytest.mark.asyncio
    async def test_flow_inline_with_condition(self):
        """Agent с inline кодом и условными переходами."""
        config = AgentConfig(
            agent_id="condition_inline",
            name="Condition Inline",
            entry="check",
            nodes={
                "check": {
                    "type": "function",
                    "code": """
def run(state):
    value = state.get('input', 0)
    state['is_positive'] = value > 0
    return state
"""
                },
                "positive": {
                    "type": "function",
                    "code": """
def run(state):
    state['result'] = 'positive_path'
    return state
"""
                },
                "negative": {
                    "type": "function",
                    "code": """
def run(state):
    state['result'] = 'negative_path'
    return state
"""
                }
            },
            edges=[
                Edge(from_node="check", to_node="positive", condition="is_positive == true"),
                Edge(from_node="check", to_node="negative", condition="is_positive == false"),
                Edge(from_node="positive", to_node=None),
                Edge(from_node="negative", to_node=None)
            ]
        )
        
        flow = await Agent.from_config(
            config={
                "id": config.agent_id,
                "name": config.name,
                "entry": config.entry,
                "nodes": config.nodes,
                "edges": config.edges
            },
            variables={}
        )
        
        # Позитивный путь
        state1 = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            input=10
        )
        result1 = await flow.run(state1)
        assert result1["result"] == "positive_path"
        
        # Негативный путь
        state2 = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            input=-5
        )
        result2 = await flow.run(state2)
        assert result2["result"] == "negative_path"

    @pytest.mark.asyncio
    async def test_flow_inline_error_handling(self):
        """Ошибка в inline коде пробрасывается."""
        config = AgentConfig(
            agent_id="error_inline",
            name="Error Inline",
            entry="bad",
            nodes={
                "bad": {
                    "type": "function",
                    "code": """
def run(state):
    raise ValueError("Intentional error")
"""
                }
            },
            edges=[
                Edge(from_node="bad", to_node=None)
            ]
        )
        
        flow = await Agent.from_config(
            config={
                "id": config.agent_id,
                "name": config.name,
                "entry": config.entry,
                "nodes": config.nodes,
                "edges": config.edges
            },
            variables={}
        )
        
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        with pytest.raises(ValueError, match="Intentional error"):
            await flow.run(state)


class TestMixedNodes:
    """Тесты комбинации inline и reference нод."""

    @pytest.mark.asyncio
    async def test_inline_after_inline(self):
        """Комбинация двух inline нод."""
        config = AgentConfig(
            agent_id="mixed_flow",
            name="Mixed Agent",
            entry="first",
            nodes={
                "first": {
                    "type": "function",
                    "code": """
def run(state):
    state['first_done'] = True
    state['counter'] = 1
    return state
"""
                },
                "second": {
                    "type": "function",
                    "code": """
def run(state):
    state['second_done'] = True
    state['counter'] = state.get('counter', 0) + 1
    return state
"""
                }
            },
            edges=[
                Edge(from_node="first", to_node="second"),
                Edge(from_node="second", to_node=None)
            ]
        )
        
        flow = await Agent.from_config(
            config={
                "id": config.agent_id,
                "name": config.name,
                "entry": config.entry,
                "nodes": config.nodes,
                "edges": config.edges
            },
            variables={}
        )
        
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await flow.run(state)
        
        assert result.get("first_done") is True
        assert result.get("second_done") is True
        assert result.get("counter") == 2


class TestInlineTool:
    """Тесты для inline tools."""

    @pytest.mark.asyncio
    async def test_inline_tool_simple(self):
        """Простой inline tool."""
        code = """
def execute(args, state):
    x = args.get('x', 0)
    y = args.get('y', 0)
    return x + y
"""
        tool = InlineTool(
            tool_id="add",
            code=code,
            description="Сложение двух чисел"
        )
        
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await tool.run({"x": 10, "y": 5}, state)
        assert result == 15

    @pytest.mark.asyncio
    async def test_inline_tool_async(self):
        """Async inline tool."""
        code = """
async def execute(args, state):
    value = args.get('value', 0)
    return value * 2
"""
        tool = InlineTool(
            tool_id="double",
            code=code
        )
        
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await tool.run({"value": 21}, state)
        assert result == 42

    @pytest.mark.asyncio
    async def test_inline_tool_with_state(self):
        """Inline tool с доступом к state."""
        code = """
def execute(args, state):
    prefix = state.get('prefix', '')
    name = args.get('name', 'World')
    return f"{prefix}Hello, {name}!"
"""
        tool = InlineTool(
            tool_id="greet",
            code=code
        )
        
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            prefix="[Bot] "
        )
        result = await tool.run({"name": "Alice"}, state)
        assert result == "[Bot] Hello, Alice!"

    @pytest.mark.asyncio
    async def test_inline_tool_with_json(self):
        """Inline tool использующий json."""
        code = """
import json

def execute(args, state):
    data = args.get('data', '{}')
    parsed = json.loads(data)
    return parsed.get('name', 'unknown')
"""
        tool = InlineTool(
            tool_id="parse_name",
            code=code
        )
        
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await tool.run({"data": '{"name": "Test"}'}, state)
        assert result == "Test"

    @pytest.mark.asyncio
    async def test_inline_tool_blocked_import(self):
        """Inline tool блокирует опасные импорты."""
        code = """
import os

def execute(args, state):
    return os.listdir('/')
"""
        tool = InlineTool(
            tool_id="bad_tool",
            code=code
        )
        
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        with pytest.raises(SafeEvalError, match="Import of 'os' is not allowed"):
            await tool.run({}, state)

    @pytest.mark.asyncio
    async def test_inline_tool_schema(self):
        """Inline tool генерирует правильную schema."""
        from apps.agents.src.models.tool_reference import CallParameter
        
        params = {
            "x": CallParameter(type="number", description="First number"),
            "y": CallParameter(type="number", description="Second number")
        }
        
        tool = InlineTool(
            tool_id="add",
            code="def execute(args, state): return args['x'] + args['y']",
            description="Add two numbers",
            parameters=params
        )
        
        schema = tool.to_openai_schema()
        
        assert schema["function"]["name"] == "add"
        assert schema["function"]["description"] == "Add two numbers"
        assert "x" in schema["function"]["parameters"]["properties"]
        assert "y" in schema["function"]["parameters"]["properties"]


class TestToolRegistryInline:
    """Тесты ToolRegistry с inline tools."""

    @pytest.mark.asyncio
    async def test_tool_registry_creates_inline_tool(self, app, container):
        """ToolRegistry создаёт InlineTool."""
        # Создаём inline tool напрямую через factory с inline конфигом
        tool_config = {
            "tool_id": "test_inline_tool",
            "description": "Test inline tool",
            "code": """
def execute(args, state):
    return args.get('value', 0) * 3
"""
        }
        
        # Загружаем через factory с inline конфигом
        tool = await container.tool_registry.create_tool(tool_config)
        
        assert tool is not None
        assert isinstance(tool, InlineTool)
        assert tool.name == "test_inline_tool"
        
        # Выполняем
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await tool.run({"value": 7}, state)
        assert result == 21


class TestInlineNodeWithHttpx:
    """Тесты функциональных нод с httpx клиентом."""

    @pytest.mark.asyncio
    async def test_inline_node_with_httpx_get(self):
        """Функциональная нода с httpx.get() - реальный запрос к API."""
        code = """
async def run(state):
    # Реальный запрос к cat facts API
    response = await httpx.get("https://catfact.ninja/fact")
    
    if response.status_code == 200:
        data = response.json()
        state['cat_fact'] = data.get('fact', '')
        state['fact_length'] = data.get('length', 0)
        state['http_success'] = True
    else:
        state['http_success'] = False
        state['error'] = f"HTTP {response.status_code}"
    
    return state
"""
        node = FunctionNode(node_id="cat_facts", code=code)
        
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await node.run(state)
        
        assert result["http_success"] is True
        assert "cat_fact" in result
        assert isinstance(result["cat_fact"], str)
        assert len(result["cat_fact"]) > 0
        assert result["fact_length"] > 0

    @pytest.mark.asyncio
    async def test_inline_node_with_httpx_post(self):
        """Функциональная нода с httpx.post() - реальный запрос к API."""
        code = """
async def run(state):
    # Реальный POST запрос к JSONPlaceholder API
    response = await httpx.post(
        "https://jsonplaceholder.typicode.com/posts",
        json={
            "title": "Test Post",
            "body": "This is a test post from httpx",
            "userId": 1
        },
        headers={"Content-Type": "application/json"}
    )
    
    if response.status_code in [200, 201]:
        data = response.json()
        state['post_id'] = data.get('id')
        state['post_title'] = data.get('title')
        state['http_success'] = True
    else:
        state['http_success'] = False
        state['error'] = f"HTTP {response.status_code}: {response.text}"
    
    return state
"""
        node = FunctionNode(node_id="http_post", code=code)
        
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await node.run(state)
        
        assert result["http_success"] is True
        assert "post_id" in result
        assert result["post_id"] is not None
        assert result["post_title"] == "Test Post"

    @pytest.mark.asyncio
    async def test_inline_node_with_httpx_params(self):
        """Функциональная нода с httpx.get() с параметрами."""
        code = """
async def run(state):
    # Запрос с query параметрами
    response = await httpx.get(
        "https://catfact.ninja/facts",
        params={"limit": 2, "max_length": 100}
    )
    
    if response.status_code == 200:
        data = response.json()
        facts = data.get('data', [])
        state['facts_count'] = len(facts)
        state['http_success'] = True
        if facts:
            state['first_fact'] = facts[0].get('fact', '')
    else:
        state['http_success'] = False
        state['error'] = f"HTTP {response.status_code}"
    
    return state
"""
        node = FunctionNode(node_id="http_params", code=code)
        
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await node.run(state)
        
        assert result["http_success"] is True
        assert result["facts_count"] == 2
        assert "first_fact" in result
        assert len(result["first_fact"]) > 0

    @pytest.mark.asyncio
    async def test_inline_node_with_httpx_error_handling(self):
        """Функциональная нода с обработкой ошибок httpx."""
        code = """
async def run(state):
    # Запрос к несуществующему endpoint
    response = await httpx.get("https://catfact.ninja/nonexistent", timeout=5.0)
    
    state['status_code'] = response.status_code
    state['is_error'] = response.status_code >= 400
    
    return state
"""
        node = FunctionNode(node_id="http_error", code=code)
        
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await node.run(state)
        
        assert "status_code" in result
        assert result["is_error"] is True
        assert result["status_code"] >= 400

    @pytest.mark.asyncio
    async def test_flow_with_httpx_node(self):
        """Agent с нодой использующей httpx."""
        config = AgentConfig(
            agent_id="httpx_test",
            name="HTTP Test Agent",
            entry="fetch_data",
            nodes={
                "fetch_data": {
                    "type": "function",
                    "code": """
async def run(state):
    response = await httpx.get("https://catfact.ninja/fact")
    if response.status_code == 200:
        data = response.json()
        state['fact'] = data.get('fact', '')
        state['processed'] = True
    return state
"""
                }
            },
            edges=[
                Edge(from_node="fetch_data", to_node=None)
            ]
        )
        
        flow = await Agent.from_config(
            config={
                "id": config.agent_id,
                "name": config.name,
                "entry": config.entry,
                "nodes": config.nodes,
                "edges": config.edges
            },
            variables={}
        )
        
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        )
        result = await flow.run(state)
        
        assert result["processed"] is True
        assert "fact" in result
        assert isinstance(result["fact"], str)
        assert len(result["fact"]) > 0

