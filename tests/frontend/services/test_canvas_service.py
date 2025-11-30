"""
Тесты для CanvasService.

Используется реальная БД без моков.
"""

import pytest
import pytest_asyncio

from apps.agents.models import (
    AgentConfig,
    AgentType,
    CodeMode,
    FlowConfig,
    LLMConfig,
    ToolReference,
)
from apps.frontend.services.canvas_service import CanvasService


@pytest_asyncio.fixture
async def canvas_service(test_context, agents_service) -> CanvasService:
    """CanvasService для тестов (требует agents_service для HTTP proxy)"""
    return CanvasService()


@pytest_asyncio.fixture
async def test_react_agent(agent_repo, unique_id, test_context) -> AgentConfig:
    """Тестовый ReAct агент"""
    agent_id = unique_id("react_agent")
    agent = AgentConfig(
        agent_id=agent_id,
        name="React Agent",
        description="Agent for canvas testing",
        type=AgentType.REACT,
        code_mode=CodeMode.CODE_REFERENCE,
        prompt="You are a react agent",
        tools=[],
        llm_config=LLMConfig(model="mock-gpt-4", context_window=10000),
        source="test"
    )
    await agent_repo.set(agent)
    yield agent
    await agent_repo.delete(agent_id)


@pytest_asyncio.fixture
async def test_stategraph_agent(agent_repo, unique_id, test_context) -> AgentConfig:
    """Тестовый StateGraph агент"""
    agent_id = unique_id("stategraph_agent")
    agent = AgentConfig(
        agent_id=agent_id,
        name="StateGraph Agent",
        description="StateGraph agent for canvas testing",
        type=AgentType.STATEGRAPH,
        code_mode=CodeMode.CODE_REFERENCE,
        prompt="You are a stategraph agent",
        tools=[],
        llm_config=LLMConfig(model="mock-gpt-4", context_window=10000),
        source="test"
    )
    await agent_repo.set(agent)
    yield agent
    await agent_repo.delete(agent_id)


@pytest_asyncio.fixture
async def test_flow(flow_repo, test_react_agent, unique_id, test_context) -> FlowConfig:
    """Тестовый flow"""
    flow_id = unique_id("canvas_flow")
    flow = FlowConfig(
        flow_id=flow_id,
        name="Canvas Test Flow",
        description="Flow for canvas service testing",
        entry_point_agent=test_react_agent.agent_id,
        source="test"
    )
    await flow_repo.set(flow)
    yield flow
    await flow_repo.delete(flow_id)


@pytest_asyncio.fixture
async def test_tool(tool_repo, unique_id, test_context) -> ToolReference:
    """Тестовый инструмент"""
    tool_id = unique_id("canvas_tool")
    tool = ToolReference(
        tool_id=tool_id,
        code_mode=CodeMode.CODE_REFERENCE,
        function_path="apps.agents.tools.test_tool",
        description="Tool for canvas testing",
        params={}
    )
    await tool_repo.set(tool)
    yield tool
    await tool_repo.delete(tool_id)


class TestCanvasServiceUpdateFlowEntryPoint:
    """Тесты для update_flow_entry_point"""
    
    @pytest.mark.asyncio
    async def test_update_entry_point_from_canvas(
        self, canvas_service, test_flow, test_react_agent
    ):
        """Проверяем обновление entry_point_agent из canvas"""
        canvas_data = {
            "nodes": [
                {
                    "id": "flow_node",
                    "type": "flow_node",
                    "params": {"flow_id": test_flow.flow_id}
                },
                {
                    "id": "agent_node",
                    "type": "agent_node",
                    "params": {"agent_id": test_react_agent.agent_id}
                }
            ],
            "edges": [
                {"source": "flow_node", "target": "agent_node"}
            ]
        }
        
        await canvas_service.update_flow_entry_point(test_flow, canvas_data)
        
        assert test_flow.entry_point_agent == test_react_agent.agent_id
    
    @pytest.mark.asyncio
    async def test_no_update_without_flow_node(self, canvas_service, test_flow):
        """Проверяем что без flow_node ничего не обновляется"""
        original_entry = test_flow.entry_point_agent
        
        canvas_data = {
            "nodes": [
                {"id": "agent_node", "type": "agent_node", "params": {"agent_id": "other"}}
            ],
            "edges": []
        }
        
        await canvas_service.update_flow_entry_point(test_flow, canvas_data)
        
        assert test_flow.entry_point_agent == original_entry
    
    @pytest.mark.asyncio
    async def test_no_update_without_edge(self, canvas_service, test_flow):
        """Проверяем что без связи flow->agent ничего не обновляется"""
        original_entry = test_flow.entry_point_agent
        
        canvas_data = {
            "nodes": [
                {"id": "flow_node", "type": "flow_node", "params": {"flow_id": test_flow.flow_id}},
                {"id": "agent_node", "type": "agent_node", "params": {"agent_id": "other"}}
            ],
            "edges": []
        }
        
        await canvas_service.update_flow_entry_point(test_flow, canvas_data)
        
        assert test_flow.entry_point_agent == original_entry


class TestCanvasServiceSaveCanvasData:
    """Тесты для save_canvas_data"""
    
    @pytest.mark.asyncio
    async def test_save_canvas_data(self, canvas_service, test_flow, flow_repo, agents_service):
        """Проверяем сохранение canvas данных (зависит от agents_service)"""
        canvas_data = {
            "nodes": [
                {
                    "id": "flow_node",
                    "type": "flow_node",
                    "params": {"flow_id": test_flow.flow_id},
                    "ui": {"x": 100, "y": 100}
                }
            ],
            "edges": []
        }
        
        await canvas_service.save_canvas_data(test_flow.flow_id, canvas_data)
        
        updated_flow = await flow_repo.get(test_flow.flow_id)
        assert updated_flow.canvas_data is not None
        assert len(updated_flow.canvas_data.get("nodes", [])) == 1
    
    @pytest.mark.asyncio
    async def test_save_canvas_data_not_found(self, canvas_service):
        """Проверяем ошибку для несуществующего flow"""
        with pytest.raises(ValueError, match="not found"):
            await canvas_service.save_canvas_data("nonexistent", {"nodes": [], "edges": []})


class TestCanvasServiceUpdateReactAgents:
    """Тесты для обновления ReAct агентов из canvas"""
    
    @pytest.mark.asyncio
    async def test_update_react_agent_tools(
        self, canvas_service, test_flow, test_react_agent, test_tool, agent_repo
    ):
        """Проверяем обновление tools[] для ReAct агента"""
        canvas_data = {
            "nodes": [
                {
                    "id": "flow_node",
                    "type": "flow_node",
                    "params": {"flow_id": test_flow.flow_id}
                },
                {
                    "id": "agent_node",
                    "type": "agent_node",
                    "params": {"agent_id": test_react_agent.agent_id}
                },
                {
                    "id": "tool_node",
                    "type": "tool_node",
                    "params": {"tool_id": test_tool.tool_id, "code_mode": "code_reference"}
                }
            ],
            "edges": [
                {"source": "flow_node", "target": "agent_node"},
                {"source": "agent_node", "target": "tool_node"}
            ]
        }
        
        await canvas_service.update_agents_from_canvas(canvas_data)
        
        updated_agent = await agent_repo.get(test_react_agent.agent_id)
        assert len(updated_agent.tools) == 1
        assert updated_agent.tools[0].tool_id == test_tool.tool_id


class TestCanvasServiceUpdateStateGraphAgents:
    """Тесты для обновления StateGraph агентов из canvas"""
    
    @pytest.mark.asyncio
    async def test_update_stategraph_graph_definition(
        self, canvas_service, test_stategraph_agent, agent_repo, flow_repo, unique_id
    ):
        """Проверяем обновление graph_definition для StateGraph агента"""
        flow_id = unique_id("sg_flow")
        flow = FlowConfig(
            flow_id=flow_id,
            name="StateGraph Flow",
            entry_point_agent=test_stategraph_agent.agent_id,
            source="test"
        )
        await flow_repo.set(flow)
        
        canvas_data = {
            "nodes": [
                {
                    "id": "flow_node",
                    "type": "flow_node",
                    "params": {"flow_id": flow_id}
                },
                {
                    "id": "entry_agent_node",
                    "type": "agent_node",
                    "params": {"agent_id": test_stategraph_agent.agent_id}
                },
                {
                    "id": "process_node",
                    "type": "tool_node",
                    "params": {"name": "process"},
                    "ui": {"x": 300, "y": 100}
                }
            ],
            "edges": [
                {"source": "flow_node", "target": "entry_agent_node"},
                {"source": "entry_agent_node", "target": "process_node"}
            ]
        }
        
        await canvas_service.update_agents_from_canvas(canvas_data)
        
        updated_agent = await agent_repo.get(test_stategraph_agent.agent_id)
        assert updated_agent.graph_definition is not None
        assert len(updated_agent.graph_definition.nodes) >= 1
        
        await flow_repo.delete(flow_id)


class TestCanvasServiceHelperMethods:
    """Тесты для вспомогательных методов"""
    
    @pytest.mark.asyncio
    async def test_find_flow_node(self, canvas_service):
        """Проверяем поиск flow ноды"""
        canvas_data = {
            "nodes": [
                {"id": "flow_1", "type": "flow_node", "params": {"flow_id": "f1"}},
                {"id": "agent_1", "type": "agent_node", "params": {}}
            ]
        }
        
        flow_node = canvas_service._find_flow_node(canvas_data, "f1")
        
        assert flow_node is not None
        assert flow_node["id"] == "flow_1"
    
    @pytest.mark.asyncio
    async def test_find_flow_node_not_found(self, canvas_service):
        """Проверяем None при отсутствии flow ноды"""
        canvas_data = {
            "nodes": [
                {"id": "agent_1", "type": "agent_node", "params": {}}
            ]
        }
        
        flow_node = canvas_service._find_flow_node(canvas_data)
        
        assert flow_node is None
    
    @pytest.mark.asyncio
    async def test_find_connected_node_ids(self, canvas_service):
        """Проверяем рекурсивный поиск связанных нод"""
        canvas_data = {
            "nodes": [
                {"id": "a"},
                {"id": "b"},
                {"id": "c"},
                {"id": "d"}
            ],
            "edges": [
                {"source": "a", "target": "b"},
                {"source": "b", "target": "c"},
                {"source": "c", "target": "d"}
            ]
        }
        
        connected = canvas_service._find_connected_node_ids(canvas_data, "a")
        
        assert connected == {"a", "b", "c", "d"}
    
    @pytest.mark.asyncio
    async def test_get_node_by_id(self, canvas_service):
        """Проверяем получение ноды по ID"""
        canvas_data = {
            "nodes": [
                {"id": "node_1", "type": "agent_node"},
                {"id": "node_2", "type": "tool_node"}
            ]
        }
        
        node = canvas_service._get_node_by_id(canvas_data, "node_2")
        
        assert node is not None
        assert node["type"] == "tool_node"
    
    @pytest.mark.asyncio
    async def test_get_node_param(self, canvas_service):
        """Проверяем получение параметра ноды"""
        canvas_data = {
            "nodes": [
                {"id": "node_1", "params": {"agent_id": "my_agent", "name": "Test"}}
            ]
        }
        
        agent_id = canvas_service._get_node_param(canvas_data, "node_1", "agent_id")
        
        assert agent_id == "my_agent"
    
    @pytest.mark.asyncio
    async def test_get_node_param_not_found(self, canvas_service):
        """Проверяем None при отсутствии параметра"""
        canvas_data = {
            "nodes": [
                {"id": "node_1", "params": {}}
            ]
        }
        
        result = canvas_service._get_node_param(canvas_data, "node_1", "missing")
        
        assert result is None

