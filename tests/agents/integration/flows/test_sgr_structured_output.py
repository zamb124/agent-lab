"""
Интеграционные тесты для SGR (State Graph Reactive) паттерна.

SGR: ReactNode с Structured Output управляет flow через edges по state.

Flow:
    AgentSO -> (state.next_action == "tool1") -> ToolNode
           -> (state.next_action == "tool2") -> FunctionNode  
           -> (state.next_action == "tool3") -> RemoteAgentNode
           -> (state.next_action == "done") -> ExitNode

Каждый action возвращает управление AgentSO, который решает что делать дальше.

БЕЗ МОКОВ - используем реальный MockLLM и реальный test-a2a-agent из docker-compose.
"""

import pytest

from apps.agents.src.agent import Agent
from apps.agents.src.agent.nodes import (
    ReactNode,
    FunctionNode,
    ToolNode,
    RemoteAgentNode,
)
from apps.agents.src.models import Edge
from apps.agents.src.tools import InlineTool
from core.state import ExecutionState


def make_state(**kwargs) -> ExecutionState:
    """Создаёт ExecutionState с минимальными обязательными полями."""
    defaults = {
        "task_id": "test-task",
        "context_id": "test-context",
        "user_id": "test-user",
        "session_id": "test-agent:test-context",
        "messages": [],
        "variables": {},
    }
    defaults.update(kwargs)
    return ExecutionState(**defaults)


class TestSGRWithStructuredOutput:
    """
    Тесты SGR паттерна: ReactNode с SO управляет routing через state.
    
    AgentSO определяет next_action через Structured Output.
    Edges проверяют state.next_action и направляют к нужной ноде.
    После каждого action управление возвращается к AgentSO.
    """

    @pytest.mark.asyncio
    async def test_sgr_full_flow_tool_function_exit(self, mock_llm_with_queue):
        """
        Полный SGR flow: AgentSO -> tool1 -> AgentSO -> tool2(function) -> AgentSO -> done(exit).
        
        Проверяет:
        1. AgentSO с SO корректно устанавливает next_action
        2. Conditional edges работают по state.next_action
        3. После action управление возвращается к AgentSO
        4. Exit node корректно завершает flow
        """
        # Настраиваем MockLLM для 3 вызовов AgentSO:
        # 1й вызов: {"next_action": "tool1", "reason": "Need to fetch data"}
        # 2й вызов: {"next_action": "tool2", "reason": "Need to process data"}
        # 3й вызов: {"next_action": "done", "reason": "All done"}
        mock_llm_with_queue([
            {"type": "structured_output", "data": {"next_action": "tool1", "reason": "Need to fetch data"}},
            {"type": "structured_output", "data": {"next_action": "tool2", "reason": "Need to process data"}},
            {"type": "structured_output", "data": {"next_action": "done", "reason": "All done", "final_result": "Success"}},
        ])
        
        # AgentSO - ReactNode с Structured Output
        agent_so = ReactNode(
            node_id="agent_so",
            prompt="""You are a coordinator. Based on current state, decide next action.
Available actions: tool1, tool2, done.
Return JSON with next_action and reason.""",
            config={
                "structured_output": True,
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "next_action": {"type": "string", "enum": ["tool1", "tool2", "done"]},
                        "reason": {"type": "string"},
                        "final_result": {"type": "string"}
                    },
                    "required": ["next_action", "reason"],
                    "additionalProperties": False
                }
            }
        )
        
        # Tool1 - ToolNode (InlineTool)
        tool1 = InlineTool(
            tool_id="data_fetcher",
            code="""
def execute(args, state):
    return {"tool1_result": "Data fetched successfully", "data": [1, 2, 3]}
""",
        )
        tool1_node = ToolNode(
            node_id="tool1",
            tool=tool1,
            input_mapping={},
        )
        
        # Tool2 - FunctionNode: доступ строго через state.field
        tool2_code = """
def run(state):
    data = state.data
    processed = [x * 2 for x in data]
    return {"tool2_result": "Data processed", "processed_data": processed}
"""
        tool2_node = FunctionNode(
            node_id="tool2",
            code=tool2_code,
        )
        
        # Done - FunctionNode (exit type): строгий доступ к полям
        done_code = """
def run(state):
    return {
        "response": f"Flow completed. Final: {state.final_result}",
        "execution_log": [state.tool1_result, state.tool2_result]
    }
"""
        done_node = FunctionNode(
            node_id="done",
            code=done_code,
            config={"type": "exit"}
        )
        
        # Создаем Agent с conditional edges
        flow = Agent(
            agent_id="sgr_test",
            name="SGR Test Agent",
            entry="agent_so",
            nodes={
                "agent_so": agent_so,
                "tool1": tool1_node,
                "tool2": tool2_node,
                "done": done_node,
            },
            edges=[
                # От AgentSO к actions по условию
                Edge(from_node="agent_so", to_node="tool1", condition="next_action == 'tool1'"),
                Edge(from_node="agent_so", to_node="tool2", condition="next_action == 'tool2'"),
                Edge(from_node="agent_so", to_node="done", condition="next_action == 'done'"),
                # От actions обратно к AgentSO
                Edge(from_node="tool1", to_node="agent_so"),
                Edge(from_node="tool2", to_node="agent_so"),
                # Done - терминальный
                Edge(from_node="done", to_node=None),
            ],
            variables={},
        )
        
        # Запускаем flow
        state = make_state(content="Start the workflow")
        result = await flow.run(state)
        
        # Проверяем что все шаги выполнились
        assert result.tool1_result == "Data fetched successfully"
        assert result.data == [1, 2, 3]
        assert result.tool2_result == "Data processed"
        assert result.processed_data == [2, 4, 6]
        assert result.final_result == "Success"
        assert "Flow completed" in result.response
        assert result.execution_log == ["Data fetched successfully", "Data processed"]

    @pytest.mark.asyncio
    async def test_sgr_with_remote_agent(self, mock_llm_with_queue, test_a2a_agent):
        """
        SGR flow с RemoteAgentNode.
        
        AgentSO -> tool1 -> AgentSO -> remote_agent -> AgentSO -> done
        
        RemoteAgent - реальный test-a2a-agent из docker-compose-test.yaml.
        """
        # Настраиваем MockLLM
        mock_llm_with_queue([
            {"type": "structured_output", "data": {"next_action": "tool1", "reason": "Fetch"}},
            {"type": "structured_output", "data": {"next_action": "remote", "reason": "Process remotely"}},
            {"type": "structured_output", "data": {"next_action": "done", "reason": "Complete", "summary": "All OK"}},
        ])
        
        # AgentSO
        agent_so = ReactNode(
            node_id="agent_so",
            prompt="Coordinator",
            config={
                "structured_output": True,
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "next_action": {"type": "string"},
                        "reason": {"type": "string"},
                        "summary": {"type": "string"}
                    },
                    "required": ["next_action", "reason"]
                }
            }
        )
        
        # Tool1
        tool1 = InlineTool(
            tool_id="fetcher",
            code="def execute(args, state):\n    return {'tool1_done': True, 'payload': 'data123'}",
        )
        tool1_node = ToolNode(node_id="tool1", tool=tool1, input_mapping={})
        
        # RemoteAgent - реальный сервер из docker-compose
        remote_node = RemoteAgentNode(
            node_id="remote",
            url=test_a2a_agent,
            input_mapping={"content": "@state:payload"},
            auth_headers={"X-API-Key": "test-api-key-12345"},
        )
        
        # Done - строгий доступ к полям
        done_node = FunctionNode(
            node_id="done",
            code="""
def run(state):
    return {"final": f"Summary: {state.summary}", "remote_result": state.response}
""",
            config={"type": "exit"}
        )
        
        flow = Agent(
            agent_id="sgr_remote_test",
            name="SGR Remote Test",
            entry="agent_so",
            nodes={
                "agent_so": agent_so,
                "tool1": tool1_node,
                "remote": remote_node,
                "done": done_node,
            },
            edges=[
                Edge(from_node="agent_so", to_node="tool1", condition="next_action == 'tool1'"),
                Edge(from_node="agent_so", to_node="remote", condition="next_action == 'remote'"),
                Edge(from_node="agent_so", to_node="done", condition="next_action == 'done'"),
                Edge(from_node="tool1", to_node="agent_so"),
                Edge(from_node="remote", to_node="agent_so"),
                Edge(from_node="done", to_node=None),
            ],
            variables={},
        )
        
        state = make_state(content="Start remote flow")
        result = await flow.run(state)
        
        # Проверки
        assert result.tool1_done is True
        assert result.payload == "data123"
        assert result.summary == "All OK"
        assert "Summary: All OK" in result.final
        # RemoteAgent должен вернуть какой-то ответ
        assert result.remote_result is not None
        assert len(result.remote_result) > 0

    @pytest.mark.asyncio
    async def test_sgr_loop_with_counter(self, mock_llm_with_queue):
        """
        SGR с циклом: AgentSO вызывает action несколько раз пока не достигнет условия.
        
        AgentSO проверяет counter и решает: increment или done.
        """
        # MockLLM: 3 раза increment, потом done
        mock_llm_with_queue([
            {"type": "structured_output", "data": {"next_action": "increment", "reason": "Counter=0, need 3"}},
            {"type": "structured_output", "data": {"next_action": "increment", "reason": "Counter=1, need 3"}},
            {"type": "structured_output", "data": {"next_action": "increment", "reason": "Counter=2, need 3"}},
            {"type": "structured_output", "data": {"next_action": "done", "reason": "Counter=3, done!"}},
        ])
        
        agent_so = ReactNode(
            node_id="agent_so",
            prompt="Check counter. If < 3, return increment. Otherwise done.",
            config={
                "structured_output": True,
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "next_action": {"type": "string", "enum": ["increment", "done"]},
                        "reason": {"type": "string"}
                    },
                    "required": ["next_action", "reason"]
                }
            }
        )
        
        # Increment: инициализируем counter и history в начальном state
        increment_node = FunctionNode(
            node_id="increment",
            code="""
def run(state):
    current = state.counter
    history = state.history
    return {"counter": current + 1, "history": history + [f"inc_{current}"]}
""",
        )
        
        # Done: строгий доступ
        done_node = FunctionNode(
            node_id="done",
            code="""
def run(state):
    return {"response": f"Done! Counter={state.counter}, History={state.history}"}
""",
            config={"type": "exit"}
        )
        
        flow = Agent(
            agent_id="sgr_loop",
            name="SGR Loop Test",
            entry="agent_so",
            nodes={
                "agent_so": agent_so,
                "increment": increment_node,
                "done": done_node,
            },
            edges=[
                Edge(from_node="agent_so", to_node="increment", condition="next_action == 'increment'"),
                Edge(from_node="agent_so", to_node="done", condition="next_action == 'done'"),
                Edge(from_node="increment", to_node="agent_so"),
                Edge(from_node="done", to_node=None),
            ],
            variables={},
        )
        
        # Начальный state с counter и history
        state = make_state(counter=0, history=[])
        result = await flow.run(state)
        
        # Проверяем что цикл выполнился 3 раза
        assert result.counter == 3
        assert result.history == ["inc_0", "inc_1", "inc_2"]
        assert "Counter=3" in result.response

    @pytest.mark.asyncio
    async def test_sgr_conditional_branching(self, mock_llm_with_queue):
        """
        SGR с условным ветвлением: AgentSO выбирает путь на основе данных.
        
        Сценарий:
        - AgentSO анализирует input
        - Если "urgent" -> fast_track
        - Если "normal" -> standard_track
        - Потом done
        """
        # Тест urgent path
        mock_llm_with_queue([
            {"type": "structured_output", "data": {"next_action": "fast_track", "priority": "HIGH"}},
            {"type": "structured_output", "data": {"next_action": "done", "result": "Fast processed"}},
        ])
        
        agent_so = ReactNode(
            node_id="agent_so",
            prompt="Analyze request. Urgent -> fast_track, Normal -> standard_track, then done.",
            config={
                "structured_output": True,
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "next_action": {"type": "string"},
                        "priority": {"type": "string"},
                        "result": {"type": "string"}
                    },
                    "required": ["next_action"]
                }
            }
        )
        
        # fast_track: строгий доступ к state.priority
        fast_track = FunctionNode(
            node_id="fast_track",
            code="""
def run(state):
    return {"processed_by": "FAST", "fast_result": f"Urgent handling: {state.priority}"}
""",
        )
        
        standard_track = FunctionNode(
            node_id="standard_track",
            code="""
def run(state):
    return {"processed_by": "STANDARD", "standard_result": "Normal handling"}
""",
        )
        
        # done: строгий доступ к state.processed_by и state.result
        done_node = FunctionNode(
            node_id="done",
            code="""
def run(state):
    return {"response": f"Completed via {state.processed_by}: {state.result}"}
""",
            config={"type": "exit"}
        )
        
        flow = Agent(
            agent_id="sgr_branch",
            name="SGR Branching",
            entry="agent_so",
            nodes={
                "agent_so": agent_so,
                "fast_track": fast_track,
                "standard_track": standard_track,
                "done": done_node,
            },
            edges=[
                Edge(from_node="agent_so", to_node="fast_track", condition="next_action == 'fast_track'"),
                Edge(from_node="agent_so", to_node="standard_track", condition="next_action == 'standard_track'"),
                Edge(from_node="agent_so", to_node="done", condition="next_action == 'done'"),
                Edge(from_node="fast_track", to_node="agent_so"),
                Edge(from_node="standard_track", to_node="agent_so"),
                Edge(from_node="done", to_node=None),
            ],
            variables={},
        )
        
        state = make_state(content="URGENT: Fix critical bug")
        result = await flow.run(state)
        
        assert result.processed_by == "FAST"
        assert result.priority == "HIGH"
        assert "Fast processed" in result.result
        assert "FAST" in result.response

    @pytest.mark.asyncio
    async def test_sgr_all_node_types(self, mock_llm_with_queue, test_a2a_agent):
        """
        Полный тест SGR со ВСЕМИ типами нод:
        1. ReactNode (agent_so) - координатор с SO
        2. ToolNode (tool1) - InlineTool
        3. FunctionNode (tool2) - Python функция
        4. RemoteAgentNode (tool3) - удалённый агент из docker-compose
        5. FunctionNode (done) - exit node
        
        Flow: agent_so -> tool1 -> agent_so -> tool2 -> agent_so -> tool3 -> agent_so -> done
        """
        mock_llm_with_queue([
            {"type": "structured_output", "data": {"next_action": "tool1", "step": 1}},
            {"type": "structured_output", "data": {"next_action": "tool2", "step": 2}},
            {"type": "structured_output", "data": {"next_action": "tool3", "step": 3}},
            {"type": "structured_output", "data": {"next_action": "done", "step": 4, "summary": "All 4 steps completed"}},
        ])
        
        # 1. AgentSO - ReactNode с Structured Output
        agent_so = ReactNode(
            node_id="agent_so",
            prompt="Coordinator. Execute tool1, tool2, tool3, then done.",
            config={
                "structured_output": True,
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "next_action": {"type": "string", "enum": ["tool1", "tool2", "tool3", "done"]},
                        "step": {"type": "integer"},
                        "summary": {"type": "string"}
                    },
                    "required": ["next_action", "step"]
                }
            }
        )
        
        # 2. ToolNode - InlineTool
        tool1 = InlineTool(
            tool_id="inline_tool",
            code="""
def execute(args, state):
    return {"tool1_executed": True, "tool1_data": "from_inline_tool"}
""",
        )
        tool1_node = ToolNode(node_id="tool1", tool=tool1, input_mapping={})
        
        # 3. FunctionNode: строгий доступ к state.tool1_data
        tool2_node = FunctionNode(
            node_id="tool2",
            code="""
def run(state):
    prev = state.tool1_data
    return {"tool2_executed": True, "tool2_data": f"processed_{prev}"}
""",
        )
        
        # 4. RemoteAgentNode (реальный test-a2a-agent из docker-compose)
        tool3_node = RemoteAgentNode(
            node_id="tool3",
            url=test_a2a_agent,
            input_mapping={"content": "@state:tool2_data"},
            auth_headers={"X-API-Key": "test-api-key-12345"},
        )
        
        # 5. Exit FunctionNode: строгий доступ ко всем полям
        done_node = FunctionNode(
            node_id="done",
            code="""
def run(state):
    return {
        "final_response": f"SGR completed: {state.summary}",
        "steps_executed": {
            "tool1": state.tool1_executed,
            "tool2": state.tool2_executed,
            "tool3_response": state.response
        }
    }
""",
            config={"type": "exit"}
        )
        
        flow = Agent(
            agent_id="sgr_all_types",
            name="SGR All Types Test",
            entry="agent_so",
            nodes={
                "agent_so": agent_so,
                "tool1": tool1_node,
                "tool2": tool2_node,
                "tool3": tool3_node,
                "done": done_node,
            },
            edges=[
                # From agent_so to actions
                Edge(from_node="agent_so", to_node="tool1", condition="next_action == 'tool1'"),
                Edge(from_node="agent_so", to_node="tool2", condition="next_action == 'tool2'"),
                Edge(from_node="agent_so", to_node="tool3", condition="next_action == 'tool3'"),
                Edge(from_node="agent_so", to_node="done", condition="next_action == 'done'"),
                # From actions back to agent_so
                Edge(from_node="tool1", to_node="agent_so"),
                Edge(from_node="tool2", to_node="agent_so"),
                Edge(from_node="tool3", to_node="agent_so"),
                # Terminal
                Edge(from_node="done", to_node=None),
            ],
            variables={},
        )
        
        state = make_state(content="Execute all steps")
        result = await flow.run(state)
        
        # === Assertions ===
        
        # Tool1 (ToolNode) executed
        assert result.tool1_executed is True, "Tool1 should be executed"
        assert result.tool1_data == "from_inline_tool", "Tool1 should set tool1_data"
        
        # Tool2 (FunctionNode) executed
        assert result.tool2_executed is True, "Tool2 should be executed"
        assert result.tool2_data == "processed_from_inline_tool", "Tool2 should process tool1 data"
        
        # Tool3 (RemoteAgentNode) executed - проверяем что response есть
        assert result.response is not None, "Tool3 RemoteAgent should return response"
        assert len(result.response) > 0, "Tool3 response should not be empty"
        
        # Summary from last SO call
        assert result.summary == "All 4 steps completed", "Summary should be set from final SO"
        
        # Final response
        assert "SGR completed" in result.final_response, "Final response should contain completion message"
        assert result.steps_executed["tool1"] is True
        assert result.steps_executed["tool2"] is True
        assert result.steps_executed["tool3_response"] is not None

    @pytest.mark.asyncio
    async def test_sgr_error_recovery(self, mock_llm_with_queue):
        """
        SGR с восстановлением после ошибки.
        
        AgentSO -> risky_action (fails) -> AgentSO -> recovery -> AgentSO -> done
        
        Тестирует что SGR может обработать ошибку и перейти к recovery.
        """
        mock_llm_with_queue([
            {"type": "structured_output", "data": {"next_action": "risky", "reason": "Try risky operation"}},
            # После ошибки AgentSO видит error_occurred и решает делать recovery
            {"type": "structured_output", "data": {"next_action": "recovery", "reason": "Error detected, recovering"}},
            {"type": "structured_output", "data": {"next_action": "done", "reason": "Recovery complete", "final_status": "recovered"}},
        ])
        
        agent_so = ReactNode(
            node_id="agent_so",
            prompt="Coordinator with error handling",
            config={
                "structured_output": True,
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "next_action": {"type": "string"},
                        "reason": {"type": "string"},
                        "final_status": {"type": "string"}
                    },
                    "required": ["next_action", "reason"]
                }
            }
        )
        
        risky_node = FunctionNode(
            node_id="risky",
            code="""
def run(state):
    return {"error_occurred": True, "error_message": "Operation failed safely"}
""",
        )
        
        # recovery: строгий доступ к state.error_message
        recovery_node = FunctionNode(
            node_id="recovery",
            code="""
def run(state):
    return {"recovered": True, "recovery_log": f"Recovered from: {state.error_message}"}
""",
        )
        
        # done: строгий доступ ко всем полям
        done_node = FunctionNode(
            node_id="done",
            code="""
def run(state):
    return {
        "response": f"Flow finished with status: {state.final_status}",
        "was_recovered": state.recovered,
        "recovery_details": state.recovery_log
    }
""",
            config={"type": "exit"}
        )
        
        flow = Agent(
            agent_id="sgr_recovery",
            name="SGR Recovery Test",
            entry="agent_so",
            nodes={
                "agent_so": agent_so,
                "risky": risky_node,
                "recovery": recovery_node,
                "done": done_node,
            },
            edges=[
                Edge(from_node="agent_so", to_node="risky", condition="next_action == 'risky'"),
                Edge(from_node="agent_so", to_node="recovery", condition="next_action == 'recovery'"),
                Edge(from_node="agent_so", to_node="done", condition="next_action == 'done'"),
                Edge(from_node="risky", to_node="agent_so"),
                Edge(from_node="recovery", to_node="agent_so"),
                Edge(from_node="done", to_node=None),
            ],
            variables={},
        )
        
        state = make_state(content="Start risky flow")
        result = await flow.run(state)
        
        # Проверки
        assert result.error_occurred is True, "Error should have occurred"
        assert result.recovered is True, "Recovery should have happened"
        assert result.final_status == "recovered"
        assert "recovered" in result.response.lower()
        assert result.was_recovered is True
        assert "Recovered from: Operation failed safely" in result.recovery_details
