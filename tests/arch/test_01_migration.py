"""
Тест 1: Миграция флоу из кода в БД.

Проверяет что weather_flow и smart_flow правильно мигрируются из кода в БД
со всеми нодами, ребрами и зависимостями.
"""
import pytest
from app.db.repositories import AgentRepository, FlowRepository
from app.models import AgentType


@pytest.mark.asyncio
async def test_flows_migration_from_code(migrated_db, storage):
    """Тест миграции weather_flow и smart_flow из кода"""
    
    # 2. ПРОВЕРКА WEATHER_FLOW
    weather_flow = await flow_repo.get("app.flows.weather_flow.weather_flow_config")
    assert weather_flow is not None, "weather_flow не найден в БД"
    assert weather_flow.flow_id == "app.flows.weather_flow.weather_flow_config"
    assert weather_flow.name == "Weather Flow"
    assert weather_flow.entry_point_agent == "app.agents.weather.agent.WeatherAgent"
    
    # Проверяем что entry point агент тоже мигрировался
    weather_agent = await agent_repo.get("app.agents.weather.agent.WeatherAgent")
    assert weather_agent is not None, "WeatherAgent не мигрировался"
    assert weather_agent.type == AgentType.REACT
    assert weather_agent.function_class == "app.agents.weather.agent.WeatherAgent"
    
    # 3. ПРОВЕРКА SMART_FLOW  
    smart_flow = await flow_repo.get("app.flows.smart_flow.smart_flow_config")
    assert smart_flow is not None, "smart_flow не найден в БД"
    assert smart_flow.flow_id == "app.flows.smart_flow.smart_flow_config"
    assert smart_flow.name == "Smart Flow"
    assert smart_flow.entry_point_agent == "app.flows.smart_flow.SmartFlowAgent"
    
    # Проверяем что SmartFlowAgent мигрировался как StateGraph
    smart_agent = await agent_repo.get("app.flows.smart_flow.SmartFlowAgent")
    assert smart_agent is not None, "SmartFlowAgent не мигрировался"
    assert smart_agent.type == AgentType.STATEGRAPH, f"Ожидали STATEGRAPH, получили {smart_agent.type}"
    assert smart_agent.function_class == "app.flows.smart_flow.SmartFlowAgent"
    
    # 4. ПРОВЕРКА ГРАФА SmartFlowAgent
    assert smart_agent.graph_definition is not None, "graph_definition не найден"
    
    graph_def = smart_agent.graph_definition
    assert len(graph_def.nodes) == 4, f"Ожидали 4 ноды, получили {len(graph_def.nodes)}"
    assert len(graph_def.edges) >= 6, f"Ожидали минимум 6 ребер, получили {len(graph_def.edges)}"
    
    # Проверяем ноды
    node_ids = [node.id for node in graph_def.nodes]
    expected_nodes = ["router", "calculator", "weather", "explainer"]
    for expected in expected_nodes:
        assert expected in node_ids, f"Нода {expected} не найдена в графе"
    
    # Проверяем entry point
    assert graph_def.entry_point == "START"
    
    # 5. ПРОВЕРКА ЗАВИСИМЫХ АГЕНТОВ
    # Все агенты используемые в SmartFlowAgent должны быть мигрированы
    calculator_agent = await agent_repo.get("app.agents.calculator.agent.CalculatorAgent")
    assert calculator_agent is not None, "CalculatorAgent не мигрировался"
    assert calculator_agent.type == AgentType.REACT
    
    explainer_agent = await agent_repo.get("app.agents.explainer.agent.ExplainerAgent")
    assert explainer_agent is not None, "ExplainerAgent не мигрировался"
    assert explainer_agent.type == AgentType.REACT
        
    print("✅ Все флоу и агенты успешно мигрированы из кода в БД!")
