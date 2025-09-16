"""
Тест 1: Миграция флоу из кода в БД.

Проверяет что weather_flow и smart_flow правильно мигрируются из кода в БД
со всеми нодами, ребрами и зависимостями.
"""
import pytest
import asyncio
from pathlib import Path
import sys

# Добавляем backend в путь
backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.core.migrator import Migrator
from app.core.storage import Storage
from app.core.models import AgentType


async def _test_flows_migration_from_code():
    """Тест миграции weather_flow и smart_flow из кода"""
    
    # 1. ЗАПУСК МИГРАЦИИ
    migrator = Migrator()
    await migrator.run_full_migration()
    
    storage = Storage()
    
    # 2. ПРОВЕРКА WEATHER_FLOW
    weather_flow = await storage.get_flow_config("weather_flow")
    assert weather_flow is not None, "weather_flow не найден в БД"
    assert weather_flow.flow_id == "weather_flow"
    assert weather_flow.name == "Weather Flow"
    assert weather_flow.entry_point_agent == "app.agents.weather.agent.WeatherAgent"
    
    # Проверяем что entry point агент тоже мигрировался
    weather_agent = await storage.get_agent_config("app.agents.weather.agent.WeatherAgent")
    assert weather_agent is not None, "WeatherAgent не мигрировался"
    assert weather_agent.type == AgentType.REACT
    assert weather_agent.function_class == "app.agents.weather.agent.WeatherAgent"
    
    # 3. ПРОВЕРКА SMART_FLOW  
    smart_flow = await storage.get_flow_config("smart_flow")
    assert smart_flow is not None, "smart_flow не найден в БД"
    assert smart_flow.flow_id == "smart_flow"
    assert smart_flow.name == "Smart Flow"
    assert smart_flow.entry_point_agent == "app.flows.smart_flow.SmartFlowAgent"
    
    # Проверяем что SmartFlowAgent мигрировался как StateGraph
    smart_agent = await storage.get_agent_config("app.flows.smart_flow.SmartFlowAgent")
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
    calculator_agent = await storage.get_agent_config("app.agents.calculator.agent.CalculatorAgent")
    assert calculator_agent is not None, "CalculatorAgent не мигрировался"
    assert calculator_agent.type == AgentType.REACT
    
    explainer_agent = await storage.get_agent_config("app.agents.explainer.agent.ExplainerAgent")
    assert explainer_agent is not None, "ExplainerAgent не мигрировался"
    assert explainer_agent.type == AgentType.REACT
        
    print("✅ Все флоу и агенты успешно мигрированы из кода в БД!")


@pytest.mark.asyncio
async def test_migration():
    """Pytest тест миграции"""
    await _test_flows_migration_from_code()


if __name__ == "__main__":
    # Прямой запуск для отладки
    asyncio.run(_test_flows_migration_from_code())
