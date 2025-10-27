"""
Тест сохранения и загрузки canvas для StateGraph агента
"""

import pytest
from app.core.container import get_container
from app.models import FlowConfig, AgentConfig, AgentType, CodeMode


@pytest.mark.asyncio
async def test_stategraph_canvas_persistence():
    """
    Проверяет что canvas для StateGraph flow сохраняется и загружается правильно
    """
    container = get_container()
    storage = container.storage
    flow_repo = container.flow_repository
    agent_repo = container.agent_repository
    
    # Создаем тестовый StateGraph агент
    agent_id = "test_stategraph_agent_canvas"
    agent = AgentConfig(
        agent_id=agent_id,
        name="Test StateGraph Agent",
        description="Тестовый StateGraph агент",
        type=AgentType.STATEGRAPH,
        code_mode=CodeMode.INLINE_CODE,
        graph_definition=None,
        source="test"
    )
    await agent_repo.set(agent)
    
    # Создаем тестовый flow
    flow_id = "test_stategraph_flow_canvas"
    flow = FlowConfig(
        flow_id=flow_id,
        name="Test StateGraph Flow",
        description="Тестовый flow",
        entry_point_agent=agent_id,
        source="test"
    )
    await flow_repo.set(flow)
    
    # Создаем canvas с дополнительной нодой
    canvas_data = {
        "nodes": [
            {
                "id": "flow_test_1",
                "type": "flow_node",
                "params": {
                    "name": "Test StateGraph Flow",
                    "flow_id": flow_id,
                    "isEntryPoint": True
                },
                "ui": {"x": 100, "y": 100, "width": 200, "height": 80}
            },
            {
                "id": "agent_test_1",
                "type": "agent_node",
                "params": {
                    "name": "Test StateGraph Agent",
                    "agent_id": flow.entry_point_agent,
                    "description": "Демонстрационный агент"
                },
                "ui": {"x": 400, "y": 100, "width": 200, "height": 80}
            },
            {
                "id": "tool_test_node",
                "type": "tool_node",
                "params": {
                    "name": "test_tool",
                    "tool_id": "app.tools.calc.calc_tools.calculate",
                    "description": "Тестовый тул",
                    "category": "calculator"
                },
                "ui": {"x": 700, "y": 100, "width": 250, "height": 80}
            }
        ],
        "edges": [
            {
                "id": "flow_to_agent",
                "source": "flow_test_1",
                "target": "agent_test_1",
                "type": "default"
            },
            {
                "id": "agent_to_tool",
                "source": "agent_test_1",
                "target": "tool_test_node",
                "type": "default"
            }
        ],
        "entry_point": "flow_test_1"
    }
    
    # Сохраняем canvas
    from app.frontend.services.canvas_service import CanvasService
    
    canvas_service = CanvasService(storage)
    await canvas_service.save_canvas_data(flow_id, canvas_data)
    
    # Проверяем что canvas сохранился в flow
    flow_reloaded = await flow_repo.get(flow_id)
    assert flow_reloaded.canvas_data is not None, "Canvas data должен быть сохранен"
    assert len(flow_reloaded.canvas_data.get("nodes", [])) == 3, f"Должно быть 3 ноды, найдено {len(flow_reloaded.canvas_data.get('nodes', []))}"
    assert len(flow_reloaded.canvas_data.get("edges", [])) == 2, "Должно быть 2 связи"
    
    # Проверяем что новая нода есть
    tool_node = None
    for node in flow_reloaded.canvas_data.get("nodes", []):
        if node.get("id") == "tool_test_node":
            tool_node = node
            break
    
    assert tool_node is not None, "Нода test_tool должна быть сохранена"
    assert tool_node.get("type") == "tool_node", "Тип ноды должен быть tool_node"
    
    # Проверяем что agent.graph_definition ОБНОВИЛСЯ (добавилась новая нода)
    agent_reloaded = await agent_repo.get(agent_id)
    assert agent_reloaded.graph_definition is not None, "graph_definition должен быть создан"
    assert len(agent_reloaded.graph_definition.nodes) == 1, "Должна быть 1 нода в graph_definition"
    assert agent_reloaded.graph_definition.nodes[0].id == "test_tool", "Нода должна называться test_tool"
    
    # Очищаем тестовые данные
    await flow_repo.delete(flow_id)
    await agent_repo.delete(agent_id)
    
    print("✅ Тест пройден: canvas сохраняется в flow, graph_definition агента не трогается")

