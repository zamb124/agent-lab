"""
Интеграционные тесты: LlmNode с ВСЕМИ типами нод как tools.

КРИТИЧЕСКИ ВАЖНО:
- После КАЖДОГО tool call state ДОЛЖЕН измениться
- Все tools реально выполняются (не mock)
- Mock только LLM
- Проверяем state после каждой итерации
"""

import pytest

from apps.flows.src.container import get_container
from apps.flows.src.models import Edge, FlowConfig
from apps.flows.src.models.enums import NodeType
from apps.flows.src.runtime.nodes import LlmNode
from apps.flows.src.tools.node_wrapper import NodeAsToolWrapper
from core.state import ExecutionState


def make_state(**kwargs) -> ExecutionState:
    """Создаёт ExecutionState."""
    defaults = {
        "task_id": "test-task",
        "context_id": "test-context",
        "user_id": "test-user",
        "session_id": "test-agent:test-context",
    }
    defaults.update(kwargs)
    return ExecutionState(**defaults)


class TestReactToolsModifyState:
    """
    КАЖДЫЙ tool call ДОЛЖЕН изменить state.
    Проверяем через tool_results и state атрибуты.
    """

    @pytest.mark.asyncio
    async def test_each_tool_call_modifies_state(self, mock_llm_with_queue):
        """
        3 tool calls подряд - каждый записывает в state.
        После каждого tool_results обновляется.
        """
        # Tool 1: записывает step1_done=True
        tool1 = {
            "tool_id": "step1_tool",
            "type": "code",
            "description": "Первый шаг",
            "args_schema": {"value": {"type": "integer"}},
            "input_mapping": {"value": "@state:value"},
            "code": """
async def execute(args, state):
    state.step1_done = True
    state.step1_value = args['value'] * 2
    return {'step1': 'completed', 'result': state.step1_value}
""",
        }

        # Tool 2: записывает step2_done=True, использует результат step1
        tool2 = {
            "tool_id": "step2_tool",
            "type": "code",
            "description": "Второй шаг",
            "args_schema": {"multiplier": {"type": "integer"}},
            "input_mapping": {"multiplier": "@state:multiplier"},
            "code": """
async def execute(args, state):
    state.step2_done = True
    state.step2_value = state.step1_value * args['multiplier']
    return {'step2': 'completed', 'result': state.step2_value}
""",
        }

        # Tool 3: финальный шаг
        tool3 = {
            "tool_id": "step3_tool",
            "type": "code",
            "description": "Третий шаг",
            "args_schema": {"suffix": {"type": "string"}},
            "input_mapping": {"suffix": "@state:suffix"},
            "code": """
async def execute(args, state):
    state.step3_done = True
    state.final_result = f"Result: {state.step2_value}{args['suffix']}"
    return {'step3': 'completed', 'final': state.final_result}
""",
        }

        mock_llm_with_queue([
            # Tool call 1
            {"type": "tool_call", "tool": "step1_tool", "args": {"value": 5}},
            # Tool call 2
            {"type": "tool_call", "tool": "step2_tool", "args": {"multiplier": 3}},
            # Tool call 3
            {"type": "tool_call", "tool": "step3_tool", "args": {"suffix": "!"}},
            # Final
            {"type": "text", "content": "All steps completed"},
        ])

        llm_node = LlmNode(
            node_id="pipeline",
            config={
                "prompt": "Execute steps in order.",
                "tools": [tool1, tool2, tool3],
            }
        )

        state = make_state(content="Run pipeline")
        result = await llm_node.run(state)

        # ПРОВЕРЯЕМ ЧТО КАЖДЫЙ TOOL ИЗМЕНИЛ STATE
        # Step 1: value=5 -> step1_value = 5*2 = 10
        assert result.step1_done is True, "step1 должен был выполниться"
        assert result.step1_value == 10, "step1: 5*2=10"

        # Step 2: step1_value=10, multiplier=3 -> step2_value = 10*3 = 30
        assert result.step2_done is True, "step2 должен был выполниться"
        assert result.step2_value == 30, "step2: 10*3=30"

        # Step 3: step2_value=30, suffix="!" -> final_result = "Result: 30!"
        assert result.step3_done is True, "step3 должен был выполниться"
        assert result.final_result == "Result: 30!", f"step3: got {result.final_result}"

        # Проверяем tool_results тоже
        assert "step1_tool" in result.tool_results
        assert "step2_tool" in result.tool_results
        assert "step3_tool" in result.tool_results

    @pytest.mark.asyncio
    async def test_tool_reads_previous_tool_state_changes(self, mock_llm_with_queue):
        """
        Tool 2 ЧИТАЕТ изменения которые сделал Tool 1.
        Это доказывает что state передается между tools.
        """
        # Tool 1: создает список
        init_tool = {
            "tool_id": "init_list",
            "type": "code",
            "description": "Создает список",
            "args_schema": {"items": {"type": "array"}},
            "input_mapping": {"items": "@state:items"},
            "code": """
async def execute(args, state):
    state.my_list = args['items']
    state.list_created = True
    return {'status': 'list created', 'count': len(state.my_list)}
""",
        }

        # Tool 2: добавляет в список (ЧИТАЕТ state.my_list от tool 1)
        append_tool = {
            "tool_id": "append_item",
            "type": "code",
            "description": "Добавляет в список",
            "args_schema": {"item": {"type": "integer"}},
            "input_mapping": {"item": "@state:item"},
            "code": """
async def execute(args, state):
    state.my_list.append(args['item'])
    state.item_added = True
    return {'status': 'item added', 'new_count': len(state.my_list)}
""",
        }

        # Tool 3: суммирует список
        sum_tool = {
            "tool_id": "sum_list",
            "type": "code",
            "description": "Суммирует список",
            "args_schema": {},
            "code": """
async def execute(args, state):
    state.total = sum(state.my_list)
    state.sum_done = True
    return {'total': state.total}
""",
        }

        mock_llm_with_queue([
            {"type": "tool_call", "tool": "init_list", "args": {"items": [1, 2, 3]}},
            {"type": "tool_call", "tool": "append_item", "args": {"item": 4}},
            {"type": "tool_call", "tool": "sum_list", "args": {}},
            {"type": "text", "content": "Done"},
        ])

        llm_node = LlmNode(
            node_id="list_processor",
            config={
                "prompt": "Process list.",
                "tools": [init_tool, append_tool, sum_tool],
            }
        )

        state = make_state(content="Process list")
        result = await llm_node.run(state)

        # Tool 1 создал список
        assert result.list_created is True
        assert result.my_list == [1, 2, 3, 4], f"Список должен быть [1,2,3,4], got {result.my_list}"

        # Tool 2 добавил элемент (значит он ПРОЧИТАЛ my_list от tool 1)
        assert result.item_added is True

        # Tool 3 посчитал сумму (значит он ПРОЧИТАЛ my_list после tool 2)
        assert result.sum_done is True
        assert result.total == 10, f"Сумма 1+2+3+4=10, got {result.total}"


class TestCodeNodeWithNamedParams:
    """CodeNode получает именованные параметры."""

    @pytest.mark.asyncio
    async def test_all_param_types(self, mock_llm_with_queue):
        """Все типы параметров передаются корректно."""
        tool = {
            "tool_id": "typed_tool",
            "type": "code",
            "description": "Tool с разными типами",
            "args_schema": {
                "str_param": {"type": "string"},
                "int_param": {"type": "integer"},
                "float_param": {"type": "number"},
                "bool_param": {"type": "boolean"},
                "list_param": {"type": "array"},
                "dict_param": {"type": "object"},
            },
            "input_mapping": {
                "str_param": "@state:str_param",
                "int_param": "@state:int_param",
                "float_param": "@state:float_param",
                "bool_param": "@state:bool_param",
                "list_param": "@state:list_param",
                "dict_param": "@state:dict_param",
            },
            "code": """
async def execute(args, state):
    state.received_str = args['str_param']
    state.received_int = args['int_param']
    state.received_float = args['float_param']
    state.received_bool = args['bool_param']
    state.received_list = args['list_param']
    state.received_dict = args['dict_param']
    state.all_received = True
    return {'status': 'all params received'}
""",
        }

        mock_llm_with_queue([
            {
                "type": "tool_call",
                "tool": "typed_tool",
                "args": {
                    "str_param": "hello",
                    "int_param": 42,
                    "float_param": 3.14,
                    "bool_param": True,
                    "list_param": [1, 2, 3],
                    "dict_param": {"key": "value"},
                }
            },
            {"type": "text", "content": "Done"},
        ])

        llm_node = LlmNode(
            node_id="param_tester",
            config={"prompt": "Test.", "tools": [tool]}
        )

        state = make_state(content="Test params")
        result = await llm_node.run(state)

        # Проверяем ВСЕ параметры
        assert result.all_received is True
        assert result.received_str == "hello"
        assert result.received_int == 42
        assert result.received_float == 3.14
        assert result.received_bool is True
        assert result.received_list == [1, 2, 3]
        assert result.received_dict == {"key": "value"}


class TestAgentSkillsAsTools:
    """Разные skills агента как tools."""

    @pytest.mark.asyncio
    async def test_different_skills_modify_state(self, mock_llm_with_queue, app):
        """
        Вызываем разные skills одного агента.
        КАЖДЫЙ skill ДОЛЖЕН изменить state.
        """
        container = get_container()

        flow_config = FlowConfig(
            flow_id="skills_agent",
            name="Skills Agent",
            entry="default",
            nodes={
                "default": {
                    "type": "code",
                    "code": "async def execute(args, state): return state",
                }
            },
            edges=[Edge(from_node="default", to_node=None)],
            branches={
                "math_skill": {
                    "name": "Math Skill",
                    "entry": "calc",
                    "nodes": {
                        "calc": {
                            "type": "code",
                            "input_mapping": {"x": "@state:x", "y": "@state:y"},
                            "code": """
async def execute(args, state):
    state.math_executed = True
    state.math_result = args['x'] + args['y']
    state.response = f"Math: {state.math_result}"
    return state
""",
                        }
                    },
                    "edges": [{"from_node": "calc", "to_node": None}],
                },
                "text_skill": {
                    "name": "Text Skill",
                    "entry": "process",
                    "nodes": {
                        "process": {
                            "type": "code",
                            "input_mapping": {"text": "@state:text"},
                            "code": """
async def execute(args, state):
    state.text_executed = True
    state.text_result = args['text'].upper()
    state.response = f"Text: {state.text_result}"
    return state
""",
                        }
                    },
                    "edges": [{"from_node": "process", "to_node": None}],
                },
            },
        )
        await container.flow_repository.set(flow_config)

        math_tool = {
            "tool_id": "do_math",
            "type": "flow",
            "description": "Math",
            "flow_id": "skills_agent",
            "branch_id": "math_skill",
            "args_schema": {"x": {"type": "integer"}, "y": {"type": "integer"}},
        }

        text_tool = {
            "tool_id": "do_text",
            "type": "flow",
            "description": "Text",
            "flow_id": "skills_agent",
            "branch_id": "text_skill",
            "args_schema": {"text": {"type": "string"}},
        }

        mock_llm_with_queue([
            {"type": "tool_call", "tool": "do_math", "args": {"x": 10, "y": 20}},
            {"type": "tool_call", "tool": "do_text", "args": {"text": "hello"}},
            {"type": "text", "content": "Skills executed"},
        ])

        llm_node = LlmNode(
            node_id="skill_coordinator",
            config={
                "prompt": "Use skills.",
                "tools": [math_tool, text_tool],
            }
        )

        state = make_state(content="Use skills")
        result = await llm_node.run(state)

        # ПРОВЕРЯЕМ ЧТО КАЖДЫЙ SKILL ИЗМЕНИЛ STATE
        assert result.math_executed is True, "math skill должен был выполниться"
        assert result.math_result == 30, "math: 10+20=30"

        assert result.text_executed is True, "text skill должен был выполниться"
        assert result.text_result == "HELLO", "text: hello -> HELLO"

        # Cleanup
        await container.flow_repository.delete("skills_agent")


class TestAllNodeTypesAsToolsWithStateChange:
    """
    ВСЕ ТИПЫ НОД участвуют как tools и изменяют state.
    Это главный архитектурный тест.
    """

    @pytest.mark.asyncio
    async def test_code_node_as_tool_modifies_state(self, mock_llm_with_queue):
        """CODE node как tool изменяет state."""
        tool = {
            "tool_id": "code_tool",
            "type": "code",
            "description": "Code tool",
            "args_schema": {"value": {"type": "integer"}},
            "input_mapping": {"value": "@state:value"},
            "code": """
async def execute(args, state):
    state.code_executed = True
    state.code_result = args['value'] * 100
    return {'result': state.code_result}
""",
        }

        mock_llm_with_queue([
            {"type": "tool_call", "tool": "code_tool", "args": {"value": 5}},
            {"type": "text", "content": "Done"},
        ])

        react = LlmNode("test", config={"prompt": "Use tool.", "tools": [tool]})
        result = await react.run(make_state(content="test"))

        assert result.code_executed is True, "CODE должен изменить state"
        assert result.code_result == 500, "CODE: 5*100=500"

    @pytest.mark.asyncio
    async def test_llm_node_as_tool_modifies_state(self, mock_llm_with_queue):
        """LLM_NODE (subagent) как tool изменяет state."""
        subagent_tool = {
            "tool_id": "subagent",
            "type": "llm_node",
            "description": "Subagent",
            "prompt": "You are a helper. Set helper_done=True in state.",
            "tools": [{
                "tool_id": "set_flag",
                "type": "code",
                "description": "Set flag",
                "code": """
async def execute(args, state):
    state.helper_flag = True
    state.helper_value = 42
    return {'status': 'flag set'}
""",
            }],
        }

        mock_llm_with_queue([
            # Main agent вызывает subagent
            {"type": "tool_call", "tool": "subagent", "args": {"request": "run helper"}},
            # Subagent вызывает свой tool
            {"type": "tool_call", "tool": "set_flag", "args": {}},
            # Subagent отвечает
            {"type": "text", "content": "Helper done"},
            # Main agent отвечает
            {"type": "text", "content": "All done"},
        ])

        react = LlmNode("main", config={"prompt": "Use subagent.", "tools": [subagent_tool]})
        result = await react.run(make_state(content="test"))

        assert result.helper_flag is True, "LLM_NODE subagent должен изменить state"
        assert result.helper_value == 42, "LLM_NODE: helper_value=42"

    @pytest.mark.asyncio
    async def test_agent_node_as_tool_modifies_state(self, mock_llm_with_queue, app):
        """AGENT (skill) как tool изменяет state."""
        container = get_container()

        flow_config = FlowConfig(
            flow_id="skill_test_agent",
            name="Skill Agent",
            entry="main",
            nodes={"main": {"type": "code", "code": "async def execute(args, state): return state"}},
            edges=[Edge(from_node="main", to_node=None)],
            branches={
                "my_skill": {
                    "name": "My Skill",
                    "entry": "do_work",
                    "nodes": {
                        "do_work": {
                            "type": "code",
                            "input_mapping": {"param": "@state:param"},
                            "code": """
async def execute(args, state):
    state.skill_executed = True
    state.skill_result = f"skill:{args['param']}"
    state.response = state.skill_result
    return state
""",
                        }
                    },
                    "edges": [{"from_node": "do_work", "to_node": None}],
                },
            },
        )
        await container.flow_repository.set(flow_config)

        tool = {
            "tool_id": "skill_tool",
            "type": "flow",
            "description": "Skill",
            "flow_id": "skill_test_agent",
            "branch_id": "my_skill",
            "args_schema": {"param": {"type": "string"}},
        }

        mock_llm_with_queue([
            {"type": "tool_call", "tool": "skill_tool", "args": {"param": "test_value"}},
            {"type": "text", "content": "Done"},
        ])

        react = LlmNode("main", config={"prompt": "Use skill.", "tools": [tool]})
        result = await react.run(make_state(content="test"))

        assert result.skill_executed is True, "AGENT skill должен изменить state"
        assert result.skill_result == "skill:test_value", "AGENT: skill_result"

        await container.flow_repository.delete("skill_test_agent")

    @pytest.mark.asyncio
    async def test_external_api_node_as_tool_modifies_state(self, mock_llm_with_queue):
        """EXTERNAL_API как tool изменяет state."""
        from unittest.mock import AsyncMock, patch

        tool = {
            "tool_id": "api_tool",
            "type": "external_api",
            "description": "API call",
            "url": "https://api.example.com/data",
            "method": "GET",
            "args_schema": {"query": {"type": "string"}},
        }

        mock_llm_with_queue([
            {"type": "tool_call", "tool": "api_tool", "args": {"query": "test"}},
            {"type": "text", "content": "Done"},
        ])

        # Mock HTTP response
        with patch('apps.flows.src.runtime.nodes.ExternalAPINode._run_impl', new_callable=AsyncMock) as mock_api:
            mock_api.return_value = {
                "response": "from_api",
                "api_executed": True,
                "api_data": "from_api",
            }

            react = LlmNode("main", config={"prompt": "Use API.", "tools": [tool]})
            result = await react.run(make_state(content="test"))

            # API был вызван
            assert mock_api.called, "EXTERNAL_API должен быть вызван"
            assert "api_tool" in result.tool_results, "EXTERNAL_API результат в tool_results"

    @pytest.mark.asyncio
    async def test_remote_flow_node_as_tool_modifies_state(self, mock_llm_with_queue):
        """REMOTE_FLOW (A2A) как tool изменяет state."""
        from unittest.mock import AsyncMock, patch

        tool = {
            "tool_id": "remote_tool",
            "type": "remote_flow",
            "description": "Remote A2A agent",
            "agent_url": "http://remote-agent:8080",
            "args_schema": {"request": {"type": "string"}},
        }

        mock_llm_with_queue([
            {"type": "tool_call", "tool": "remote_tool", "args": {"request": "hello"}},
            {"type": "text", "content": "Done"},
        ])

        # Mock A2A call
        with patch('apps.flows.src.runtime.nodes.RemoteFlowNode._run_impl', new_callable=AsyncMock) as mock_remote:
            mock_remote.return_value = {
                "response": "pong",
                "remote_executed": True,
                "remote_response": "pong",
            }

            react = LlmNode("main", config={"prompt": "Use remote.", "tools": [tool]})
            result = await react.run(make_state(content="test"))

            assert mock_remote.called, "REMOTE_FLOW должен быть вызван"
            assert "remote_tool" in result.tool_results, "REMOTE_FLOW результат в tool_results"

    @pytest.mark.asyncio
    async def test_mcp_node_as_tool_modifies_state(self, mock_llm_with_queue):
        """MCP как tool изменяет state."""
        from unittest.mock import AsyncMock, patch

        tool = {
            "tool_id": "mcp_tool",
            "type": "mcp",
            "description": "MCP tool",
            "mcp_server": "test_server",
            "mcp_tool": "test_tool",
            "args_schema": {"input": {"type": "string"}},
        }

        mock_llm_with_queue([
            {"type": "tool_call", "tool": "mcp_tool", "args": {"input": "data"}},
            {"type": "text", "content": "Done"},
        ])

        # Mock MCP call
        with patch('apps.flows.src.runtime.nodes.MCPNode._run_impl', new_callable=AsyncMock) as mock_mcp:
            mock_mcp.return_value = {
                "response": "mcp_result",
                "mcp_executed": True,
                "mcp_output": "mcp_result",
            }

            react = LlmNode("main", config={"prompt": "Use MCP.", "tools": [tool]})
            result = await react.run(make_state(content="test"))

            assert mock_mcp.called, "MCP должен быть вызван"
            assert "mcp_tool" in result.tool_results, "MCP результат в tool_results"


class TestAgentCallsOwnSkillsAsTools:
    """
    LlmNode агента вызывает СВОИ ЖЕ скиллы как tools.
    Это ключевой паттерн: агент может использовать свои скиллы.
    """

    @pytest.mark.asyncio
    async def test_agent_calls_own_skills_as_tools(self, mock_llm_with_queue, app):
        """
        Агент вызывает СВОИ ЖЕ скиллы как tools.

        Структура:
        - default skill: LlmNode с tools (skill_a, skill_b как tools)
        - skill_a: CodeNode - вычисление
        - skill_b: CodeNode - текст
        """
        container = get_container()

        flow_config = FlowConfig(
            flow_id="self_skill_agent",
            name="Self Skill Agent",
            entry="main_react",
            nodes={
                "main_react": {
                    "type": "llm_node",
                    "prompt": "You can use your own skills as tools.",
                    "tools": [
                        # Свой скилл A как tool
                        {
                            "tool_id": "use_skill_a",
                            "type": "flow",
                            "description": "Use Skill A - compute square",
                            "flow_id": "self_skill_agent",
                            "branch_id": "skill_a",
                            "args_schema": {"number": {"type": "integer"}},
                        },
                        # Свой скилл B как tool
                        {
                            "tool_id": "use_skill_b",
                            "type": "flow",
                            "description": "Use Skill B - uppercase text",
                            "flow_id": "self_skill_agent",
                            "branch_id": "skill_b",
                            "args_schema": {"text": {"type": "string"}},
                        },
                    ],
                },
            },
            edges=[Edge(from_node="main_react", to_node=None)],
            branches={
                "skill_a": {
                    "name": "Skill A - Math",
                    "entry": "calc",
                    "nodes": {
                        "calc": {
                            "type": "code",
                            "input_mapping": {"number": "@state:number"},
                            "code": """
async def execute(args, state):
    state.skill_a_executed = True
    state.skill_a_result = args['number'] ** 2
    state.response = f"Skill A: {state.skill_a_result}"
    return state
""",
                        }
                    },
                    "edges": [Edge(from_node="calc", to_node=None)],
                },
                "skill_b": {
                    "name": "Skill B - Text",
                    "entry": "process",
                    "nodes": {
                        "process": {
                            "type": "code",
                            "input_mapping": {"text": "@state:text"},
                            "code": """
async def execute(args, state):
    state.skill_b_executed = True
    state.skill_b_result = args['text'].upper() + "!!!"
    state.response = f"Skill B: {state.skill_b_result}"
    return state
""",
                        }
                    },
                    "edges": [Edge(from_node="process", to_node=None)],
                },
            },
        )
        await container.flow_repository.set(flow_config)

        # Mock LLM вызывает ОБА своих скилла
        mock_llm_with_queue([
            {"type": "tool_call", "tool": "use_skill_a", "args": {"number": 5}},
            {"type": "tool_call", "tool": "use_skill_b", "args": {"text": "hello"}},
            {"type": "text", "content": "Used both my skills!"},
        ])

        # Запускаем агента
        agent = await container.flow_factory.get_flow("self_skill_agent")
        state = make_state(content="Use your skills")
        result = await agent.run(state)

        # ПРОВЕРЯЕМ ЧТО ОБА СВОИХ СКИЛЛА ВЫПОЛНИЛИСЬ
        assert result.skill_a_executed is True, "Skill A должен выполниться"
        assert result.skill_a_result == 25, "Skill A: 5^2 = 25"

        assert result.skill_b_executed is True, "Skill B должен выполниться"
        assert result.skill_b_result == "HELLO!!!", "Skill B: hello -> HELLO!!!"

        await container.flow_repository.delete("self_skill_agent")

    @pytest.mark.asyncio
    async def test_agent_calls_own_and_other_agent_skills(self, mock_llm_with_queue, app):
        """
        Агент вызывает:
        1. СВОЙ скилл
        2. Скилл ДРУГОГО агента
        """
        container = get_container()

        # Агент-помощник
        helper_config = FlowConfig(
            flow_id="helper_agent",
            name="Helper Agent",
            entry="main",
            nodes={"main": {"type": "code", "code": "async def execute(args, state): return state"}},
            edges=[Edge(from_node="main", to_node=None)],
            branches={
                "helper_skill": {
                    "name": "Helper Skill",
                    "entry": "help",
                    "nodes": {
                        "help": {
                            "type": "code",
                            "input_mapping": {"request": "@state:request"},
                            "code": """
async def execute(args, state):
    state.helper_executed = True
    state.helper_response = f"Helper helped with: {args['request']}"
    state.response = state.helper_response
    return state
""",
                        }
                    },
                    "edges": [Edge(from_node="help", to_node=None)],
                },
            },
        )
        await container.flow_repository.set(helper_config)

        # Главный агент
        main_config = FlowConfig(
            flow_id="main_agent",
            name="Main Agent",
            entry="main_react",
            nodes={
                "main_react": {
                    "type": "llm_node",
                    "prompt": "You can use your skills and other agent skills.",
                    "tools": [
                        # СВОЙ скилл
                        {
                            "tool_id": "my_skill",
                            "type": "flow",
                            "description": "My own skill",
                            "flow_id": "main_agent",  # СВОЙ
                            "branch_id": "own_skill",
                            "args_schema": {"value": {"type": "integer"}},
                        },
                        # Скилл ДРУГОГО агента
                        {
                            "tool_id": "helper_skill",
                            "type": "flow",
                            "description": "Helper agent skill",
                            "flow_id": "helper_agent",  # ДРУГОЙ агент
                            "branch_id": "helper_skill",
                            "args_schema": {"request": {"type": "string"}},
                        },
                    ],
                },
            },
            edges=[Edge(from_node="main_react", to_node=None)],
            branches={
                "own_skill": {
                    "name": "Own Skill",
                    "entry": "do_own",
                    "nodes": {
                        "do_own": {
                            "type": "code",
                            "input_mapping": {"value": "@state:value"},
                            "code": """
async def execute(args, state):
    state.own_skill_executed = True
    state.own_result = args['value'] * 10
    state.response = f"Own: {state.own_result}"
    return state
""",
                        }
                    },
                    "edges": [Edge(from_node="do_own", to_node=None)],
                },
            },
        )
        await container.flow_repository.set(main_config)

        mock_llm_with_queue([
            # Вызываем СВОЙ скилл
            {"type": "tool_call", "tool": "my_skill", "args": {"value": 7}},
            # Вызываем скилл ДРУГОГО агента
            {"type": "tool_call", "tool": "helper_skill", "args": {"request": "help me"}},
            {"type": "text", "content": "Done with both!"},
        ])

        agent = await container.flow_factory.get_flow("main_agent")
        state = make_state(content="Use skills")
        result = await agent.run(state)

        # СВОЙ скилл выполнился
        assert result.own_skill_executed is True, "Own skill должен выполниться"
        assert result.own_result == 70, "Own skill: 7*10=70"

        # Скилл ДРУГОГО агента выполнился
        assert result.helper_executed is True, "Helper skill должен выполниться"
        assert "help me" in result.helper_response, "Helper обработал запрос"

        # Cleanup
        await container.flow_repository.delete("main_agent")
        await container.flow_repository.delete("helper_agent")


class TestParallelToolExecution:
    """
    Тесты ПАРАЛЛЕЛЬНОГО выполнения tools.
    Когда LLM возвращает несколько tool_calls в одном ответе.
    """

    @pytest.mark.asyncio
    async def test_parallel_tools_all_results_in_messages(self, mock_llm_with_queue):
        """
        LLM возвращает 3 tool_calls ОДНОВРЕМЕННО.
        Все 3 должны выполниться ПАРАЛЛЕЛЬНО.
        ВСЕ результаты должны попасть в messages.
        """

        # Список для отслеживания порядка выполнения

        # Tool 1: медленный (0.1 сек)
        tool1 = {
            "tool_id": "slow_tool",
            "type": "code",
            "description": "Slow tool",
            "args_schema": {"value": {"type": "integer"}},
            "input_mapping": {"value": "@state:value"},
            "code": """
import asyncio
async def execute(args, state):
    await asyncio.sleep(0.1)  # Медленный
    state.slow_done = True
    state.slow_result = args['value'] * 10
    return {'tool': 'slow', 'result': state.slow_result}
""",
        }

        # Tool 2: быстрый
        tool2 = {
            "tool_id": "fast_tool",
            "type": "code",
            "description": "Fast tool",
            "args_schema": {"value": {"type": "integer"}},
            "input_mapping": {"value": "@state:value"},
            "code": """
async def execute(args, state):
    state.fast_done = True
    state.fast_result = args['value'] * 100
    return {'tool': 'fast', 'result': state.fast_result}
""",
        }

        # Tool 3: средний (0.05 сек)
        tool3 = {
            "tool_id": "medium_tool",
            "type": "code",
            "description": "Medium tool",
            "args_schema": {"value": {"type": "integer"}},
            "input_mapping": {"value": "@state:value"},
            "code": """
import asyncio
async def execute(args, state):
    await asyncio.sleep(0.05)  # Средний
    state.medium_done = True
    state.medium_result = args['value'] * 50
    return {'tool': 'medium', 'result': state.medium_result}
""",
        }

        # LLM возвращает ВСЕ 3 tool_calls В ОДНОМ ОТВЕТЕ
        mock_llm_with_queue([
            # Один ответ с 3 параллельными tool_calls
            {
                "type": "tool_calls",  # Множественное!
                "calls": [
                    {"tool": "slow_tool", "args": {"value": 1}},
                    {"tool": "fast_tool", "args": {"value": 2}},
                    {"tool": "medium_tool", "args": {"value": 3}},
                ]
            },
            {"type": "text", "content": "All tools completed in parallel!"},
        ])

        llm_node = LlmNode(
            node_id="parallel_test",
            config={
                "prompt": "Execute tools.",
                "tools": [tool1, tool2, tool3],
            }
        )

        state = make_state(content="Run parallel")
        result = await llm_node.run(state)

        # ВСЕ tools выполнились
        assert result.slow_done is True, "slow_tool должен выполниться"
        assert result.fast_done is True, "fast_tool должен выполниться"
        assert result.medium_done is True, "medium_tool должен выполниться"

        # Результаты правильные
        assert result.slow_result == 10, "slow: 1*10=10"
        assert result.fast_result == 200, "fast: 2*100=200"
        assert result.medium_result == 150, "medium: 3*50=150"

        # ВСЕ результаты в tool_results
        assert "slow_tool" in result.tool_results, "slow_tool в tool_results"
        assert "fast_tool" in result.tool_results, "fast_tool в tool_results"
        assert "medium_tool" in result.tool_results, "medium_tool в tool_results"

        # ВСЕ результаты в messages (tool_result messages имеют tool_call_id в metadata)
        tool_result_messages = [
            m for m in result.messages
            if hasattr(m, "metadata") and m.metadata and m.metadata.get("tool_call_id")
        ]
        assert len(tool_result_messages) >= 3, f"Должно быть минимум 3 tool_result messages, got {len(tool_result_messages)}"

    @pytest.mark.asyncio
    async def test_parallel_execution_is_actually_parallel(self, mock_llm_with_queue):
        """
        Проверяем что tools РЕАЛЬНО выполняются параллельно.
        Если бы последовательно - 0.3 сек минимум.
        Параллельно - ~0.1 сек.
        """
        import time

        # 3 tools, каждый спит 0.1 сек
        tool0 = {
            "tool_id": "sleep_tool_0",
            "type": "code",
            "description": "Sleep tool 0",
            "args_schema": {},
            "code": """
import asyncio
async def execute(args, state):
    await asyncio.sleep(0.1)
    state.tool_0_done = True
    return {'idx': 0, 'done': True}
""",
        }
        tool1 = {
            "tool_id": "sleep_tool_1",
            "type": "code",
            "description": "Sleep tool 1",
            "args_schema": {},
            "code": """
import asyncio
async def execute(args, state):
    await asyncio.sleep(0.1)
    state.tool_1_done = True
    return {'idx': 1, 'done': True}
""",
        }
        tool2 = {
            "tool_id": "sleep_tool_2",
            "type": "code",
            "description": "Sleep tool 2",
            "args_schema": {},
            "code": """
import asyncio
async def execute(args, state):
    await asyncio.sleep(0.1)
    state.tool_2_done = True
    return {'idx': 2, 'done': True}
""",
        }
        tools = [tool0, tool1, tool2]

        # LLM вызывает все 3 параллельно
        mock_llm_with_queue([
            {
                "type": "tool_calls",
                "calls": [
                    {"tool": "sleep_tool_0", "args": {}},
                    {"tool": "sleep_tool_1", "args": {}},
                    {"tool": "sleep_tool_2", "args": {}},
                ]
            },
            {"type": "text", "content": "Done"},
        ])

        llm_node = LlmNode(
            node_id="timing_test",
            config={"prompt": "Run.", "tools": tools}
        )

        state = make_state(content="test")

        start = time.time()
        result = await llm_node.run(state)
        elapsed = time.time() - start

        # Если параллельно: ~0.1 сек
        # Если последовательно: ~0.3 сек
        assert elapsed < 0.35, f"Должно быть < 0.35 сек (параллельно), но заняло {elapsed:.2f} сек"

        # Все выполнились
        assert result.tool_0_done is True
        assert result.tool_1_done is True
        assert result.tool_2_done is True

    @pytest.mark.asyncio
    async def test_parallel_tools_state_merge_last_wins(self, mock_llm_with_queue):
        """
        При параллельном выполнении если tools пишут в одно поле,
        побеждает тот кто закончил последним.
        """
        # Tool 1: быстро записывает shared_value=100
        tool1 = {
            "tool_id": "first_writer",
            "type": "code",
            "description": "Writes fast",
            "args_schema": {},
            "code": """
async def execute(args, state):
    state.shared_value = 100
    state.first_wrote = True
    return {'wrote': 100}
""",
        }

        # Tool 2: медленнее, записывает shared_value=999
        tool2 = {
            "tool_id": "second_writer",
            "type": "code",
            "description": "Writes slow",
            "args_schema": {},
            "code": """
import asyncio
async def execute(args, state):
    await asyncio.sleep(0.05)  # Медленнее
    state.shared_value = 999
    state.second_wrote = True
    return {'wrote': 999}
""",
        }

        mock_llm_with_queue([
            {
                "type": "tool_calls",
                "calls": [
                    {"tool": "first_writer", "args": {}},
                    {"tool": "second_writer", "args": {}},
                ]
            },
            {"type": "text", "content": "Done"},
        ])

        llm_node = LlmNode(
            node_id="merge_test",
            config={"prompt": "Write.", "tools": [tool1, tool2]}
        )

        result = await llm_node.run(make_state(content="test"))

        # Оба выполнились
        assert result.first_wrote is True
        assert result.second_wrote is True

        # Второй закончил последним - его значение
        assert result.shared_value == 999, "Последний (second_writer) должен победить"


class TestNodeAsToolWrapperBasics:
    """Базовые тесты NodeAsToolWrapper."""

    def test_wrapper_supports_all_node_types(self):
        """NodeAsToolWrapper поддерживает все типы."""
        for node_type in NodeType:
            config = {
                "tool_id": f"test_{node_type.value}",
                "type": node_type.value,
                "description": "Test",
            }

            if node_type == NodeType.CODE:
                config["code"] = "async def execute(args, state): return {}"
            elif node_type == NodeType.LLM_NODE:
                config["prompt"] = "Test"
                config["tools"] = []
            elif node_type == NodeType.FLOW:
                config["flow_id"] = "test"
            elif node_type == NodeType.REMOTE_FLOW:
                config["agent_url"] = "http://test"
            elif node_type == NodeType.EXTERNAL_API:
                config["url"] = "http://test"
                config["method"] = "GET"
            elif node_type == NodeType.MCP:
                config["mcp_server"] = "test"
                config["mcp_tool"] = "test"

            wrapper = NodeAsToolWrapper(config)
            assert wrapper.name == f"test_{node_type.value}"

    def test_all_node_types_in_enum(self):
        """Все типы нод в enum."""
        expected = ["llm_node", "code", "flow", "remote_flow", "external_api", "mcp"]
        actual = [t.value for t in NodeType]
        for e in expected:
            assert e in actual
