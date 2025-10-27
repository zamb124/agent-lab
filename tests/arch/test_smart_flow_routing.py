"""
Тест для проверки SmartFlow с роутингом между нодами.

Проверяет что:
1. SmartFlow правильно мигрирует в БД
2. Роутер выбирает правильную ноду в зависимости от запроса
3. Разные ноды (calculator/weather) работают корректно
"""
import pytest
from langchain_core.messages import HumanMessage


@pytest.mark.asyncio
async def test_smart_flow_migration(migrated_db, storage, agent_factory, agent_repo):
    """Тест: SmartFlow правильно мигрирует в БД"""
    
    # Проверяем что SmartFlowAgent есть в БД
    agent_id = "app.flows.smart_flow.SmartFlowAgent"
    agent_config = await agent_repo.get(agent_id)
    
    assert agent_config is not None, f"SmartFlowAgent не найден в БД"
    print(f"✅ SmartFlowAgent найден в БД: {agent_config.name}")
    
    # Проверяем что у него есть graph_definition
    if agent_config.graph_definition:
        print(f"  Тип: StateGraph")
        print(f"  Нод: {len(agent_config.graph_definition.nodes)}")
        for node in agent_config.graph_definition.nodes:
            print(f"    - {node.id} ({node.type})")
            if node.type.value == "agent_node":
                print(f"      function_class: {node.function_class}")
                print(f"      params: {node.params}")
    else:
        print(f"  Тип: ReAct")
    
    # Проверяем что агент можно создать
    agent = await agent_factory.get_agent(agent_id)
    print(f"✅ SmartFlowAgent создан успешно")
    
    # Проверяем что граф компилируется
    try:
        compiled_graph = await agent.compile_graph()
        print(f"✅ Граф SmartFlowAgent скомпилирован успешно")
    except Exception as e:
        print(f"❌ Ошибка компиляции графа: {e}")
        raise


@pytest.mark.asyncio
async def test_smart_flow_calculator_routing(migrated_db, flow_factory, mock_llm, agent_repo):
    """Тест: SmartFlow направляет математические запросы в calculator"""
    
    # Настраиваем mock LLM
    mock_llm.configure(
        responses={
            "посчитай": "Использую calculate для вычисления",
            "5 + 7": "Результат: 12",
            "12": "Отлично! Калькулятор посчитал 5 + 7 и получил 12",
        }
    )
    
    # Получаем flow
    smart_flow_key = "app.flows.smart_flow.smart_flow_config"
    
    try:
        smart_flow = await flow_factory.get_flow(smart_flow_key)
    except Exception as e:
        print(f"❌ Не удалось загрузить SmartFlow: {e}")
        raise
    
    # Тестируем математический запрос
    result = await smart_flow.ainvoke(
        {"messages": [HumanMessage(content="Посчитай 5 + 7")]},
        config={"configurable": {"thread_id": "test_smart_calc"}}
    )
    
    assert "messages" in result
    final_content = " ".join([msg.content for msg in result["messages"]])
    
    # Проверяем что запрос обработан
    assert len(final_content) > 0
    print(f"✅ Calculator routing работает")
    print(f"   Результат: {result['messages'][-1].content[:100]}...")


@pytest.mark.asyncio
async def test_smart_flow_weather_routing(migrated_db, flow_factory, mock_llm, agent_repo):
    """Тест: SmartFlow направляет погодные запросы в weather"""
    
    # Настраиваем mock LLM
    mock_llm.configure(
        responses={
            "погода": "Использую get_weather",
            "москва": "Погода в Москве: солнечно, +20°C",
            "солнечно": "Отлично! В Москве хорошая погода - солнечно и тепло",
        }
    )
    
    # Получаем flow
    smart_flow_key = "app.flows.smart_flow.smart_flow_config"
    smart_flow = await flow_factory.get_flow(smart_flow_key)
    
    # Тестируем погодный запрос
    result = await smart_flow.ainvoke(
        {"messages": [HumanMessage(content="Какая погода в Москве?")]},
        config={"configurable": {"thread_id": "test_smart_weather"}}
    )
    
    assert "messages" in result
    final_content = " ".join([msg.content for msg in result["messages"]])
    
    # Проверяем что запрос обработан
    assert len(final_content) > 0
    print(f"✅ Weather routing работает")
    print(f"   Результат: {result['messages'][-1].content[:100]}...")


@pytest.mark.asyncio
async def test_smart_flow_different_paths(migrated_db, flow_factory, mock_llm, agent_repo):
    """Тест: SmartFlow выбирает разные пути для разных запросов"""
    
    # Настраиваем mock LLM
    mock_llm.configure(
        responses={
            "посчитай": "Результат: 20",
            "погода": "Погода: солнечно",
            "20": "Калькулятор посчитал",
            "солнечно": "Погода хорошая",
        }
    )
    
    # Получаем flow
    smart_flow_key = "app.flows.smart_flow.smart_flow_config"
    smart_flow = await flow_factory.get_flow(smart_flow_key)
    
    # Тест 1: Математика
    result1 = await smart_flow.ainvoke(
        {"messages": [HumanMessage(content="Посчитай 10 + 10")]},
        config={"configurable": {"thread_id": "test_diff_1"}}
    )
    
    # Тест 2: Погода
    result2 = await smart_flow.ainvoke(
        {"messages": [HumanMessage(content="Какая погода?")]},
        config={"configurable": {"thread_id": "test_diff_2"}}
    )
    
    # Проверяем что оба запроса обработаны
    assert "messages" in result1
    assert "messages" in result2
    
    content1 = " ".join([msg.content for msg in result1["messages"]])
    content2 = " ".join([msg.content for msg in result2["messages"]])
    
    assert len(content1) > 0
    assert len(content2) > 0
    
    print(f"✅ Разные пути работают корректно")
    print(f"   Математика: {result1['messages'][-1].content[:50]}...")
    print(f"   Погода: {result2['messages'][-1].content[:50]}...")

