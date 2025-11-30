"""
Тесты для разных типов агентов: ReActAgent и StateGraphAgent.
Проверяем что рефакторинг BaseAgent работает корректно.
"""

import pytest
from apps.agents.agents.react_agent import ReActAgent
from apps.agents.agents.stategraph_agent import StateGraphAgent
from apps.agents.models import AgentConfig, AgentType
from apps.agents.container import get_agents_container


@pytest.mark.asyncio
async def test_react_agent_requires_prompt():
    """ReAct агент требует наличия prompt в конфигурации"""
    config = AgentConfig(
        agent_id="test.react.no_prompt",
        name="Test ReAct No Prompt",
        type=AgentType.REACT,
        prompt=None
    )
    agent = ReActAgent(config)
    
    with pytest.raises(ValueError, match="требует prompt"):
        await agent.get_runner()


@pytest.mark.asyncio
async def test_react_agent_compiles_with_prompt(migrated_db):
    """ReAct агент успешно создает раннер при наличии prompt"""
    config = AgentConfig(
        agent_id="test.react.with_prompt",
        name="Test ReAct With Prompt",
        type=AgentType.REACT,
        prompt="Ты тестовый агент",
        tools=[]
    )
    agent = ReActAgent(config)
    agent.set_tools([])
    
    runner = await agent.get_runner()
    assert runner is not None


@pytest.mark.asyncio
async def test_stategraph_agent_requires_definition():
    """StateGraph агент требует наличия graph_definition в конфигурации"""
    config = AgentConfig(
        agent_id="test.stategraph.no_definition",
        name="Test StateGraph No Definition",
        type=AgentType.STATEGRAPH,
        graph_definition=None
    )
    agent = StateGraphAgent(config)
    
    with pytest.raises(NotImplementedError, match="должен определить атрибут graph_definition"):
        await agent.get_runner()


@pytest.mark.asyncio
async def test_stategraph_agent_compiles_with_definition(migrated_db):
    """StateGraph агент успешно создает раннер при наличии graph_definition"""
    config = AgentConfig(
        agent_id="test.stategraph.with_definition",
        name="Test StateGraph With Definition",
        type=AgentType.STATEGRAPH,
        graph_definition={
            "entry_point": "start",
            "nodes": [
                {
                    "id": "start",
                    "type": "message_node",
                    "config": {"message": "Привет, это тестовое сообщение"}
                }
            ],
            "edges": []
        }
    )
    agent = StateGraphAgent(config)
    
    runner = await agent.get_runner()
    assert runner is not None


@pytest.mark.asyncio
async def test_agent_factory_creates_react_agent(migrated_db):
    """AgentFactory создает ReActAgent для типа REACT"""
    config = AgentConfig(
        agent_id="test.factory.react",
        name="Test Factory ReAct",
        type=AgentType.REACT,
        prompt="Тестовый промпт",
        tools=[]
    )
    
    factory = get_agents_container().agent_factory
    agent = await factory._create_agent_instance(config)
    
    assert isinstance(agent, ReActAgent)
    assert agent.config.agent_id == "test.factory.react"


@pytest.mark.asyncio
async def test_agent_factory_creates_stategraph_agent(migrated_db):
    """AgentFactory создает StateGraphAgent для типа STATEGRAPH"""
    config = AgentConfig(
        agent_id="test.factory.stategraph",
        name="Test Factory StateGraph",
        type=AgentType.STATEGRAPH,
        graph_definition={
            "entry_point": "start",
            "nodes": [
                {
                    "id": "start",
                    "type": "message_node",
                    "config": {"message": "Привет, это тестовое сообщение"}
                }
            ],
            "edges": []
        }
    )
    
    factory = get_agents_container().agent_factory
    agent = await factory._create_agent_instance(config)
    
    assert isinstance(agent, StateGraphAgent)
    assert agent.config.agent_id == "test.factory.stategraph"


@pytest.mark.asyncio
async def test_react_agent_with_llm_config(migrated_db):
    """ReAct агент использует llm_config из конфигурации"""
    config = AgentConfig(
        agent_id="test.react.llm_config",
        name="Test ReAct LLM Config",
        type=AgentType.REACT,
        prompt="Ты тестовый агент",
        llm_config={
            "model": "mock-gpt-4",
            "temperature": 0.7,
            "max_tokens": 1000
        },
        tools=[]
    )
    agent = ReActAgent(config)
    agent.set_tools([])
    
    runner = await agent.get_runner()
    assert runner is not None


@pytest.mark.asyncio
async def test_react_agent_dynamic_prompt(migrated_db):
    """ReAct агент создает динамический промпт с переменными"""
    config = AgentConfig(
        agent_id="test.react.dynamic_prompt",
        name="Test ReAct Dynamic Prompt",
        type=AgentType.REACT,
        prompt="Привет, {user_name}! Дата: {current_date}",
        local_variables={"company_name": "Test Company"},
        tools=[]
    )
    agent = ReActAgent(config)
    agent.set_tools([])
    
    runner = await agent.get_runner()
    assert runner is not None

