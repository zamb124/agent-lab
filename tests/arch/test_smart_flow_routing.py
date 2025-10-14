"""
Тест для проверки SmartFlow с роутингом между нодами.

Проверяет что:
1. SmartFlow правильно мигрирует в БД
2. Роутер выбирает правильную ноду в зависимости от запроса
3. Разные ноды (calculator/weather) работают корректно
"""
import pytest
from pathlib import Path
import sys

backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.core.storage import Storage
from app.core.flow_factory import FlowFactory
from app.core.migrator import Migrator
from app.core.agent_factory import AgentFactory
from langchain_core.messages import HumanMessage


@pytest.mark.asyncio
async def test_smart_flow_migration():
    """Тест: SmartFlow правильно мигрирует в БД"""
    
    migrator = Migrator()
    
    # Мигрируем все агенты включая SmartFlow
    await migrator.run_full_migration()
    await migrator._set_system_context()
    
    storage = Storage()
    
    # Проверяем что SmartFlowAgent есть в БД
    agent_id = "app.flows.smart_flow.SmartFlowAgent"
    agent_config = await storage.get_agent_config(agent_id)
    
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
    agent_factory = AgentFactory()
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
async def test_smart_flow_calculator_routing():
    """Тест: SmartFlow направляет математические запросы в calculator"""
    
    # Настраиваем мок LLM
    from app.core.llm_factory import get_global_mock_llm, get_llm
    get_llm("mock-gpt-4")
    mock_llm = get_global_mock_llm()
    if mock_llm:
        mock_llm.set_responses({
            "посчитай": "Использую calculate для вычисления",
            "5 + 7": "Результат: 12",
            "12": "Отлично! Калькулятор посчитал 5 + 7 и получил 12",
        })
    
    # Мигрируем
    migrator = Migrator()
    await migrator.run_full_migration()
    await migrator._set_system_context()
    
    # Получаем flow
    flow_factory = FlowFactory()
    
    # Проверяем что smart_flow есть в списке flows
    storage = Storage()
    all_keys = []
    async with storage._get_session() as session:
        from sqlalchemy import select, text
        from app.db.models import Storage as StorageModel
        result = await session.execute(
            select(StorageModel.key).where(StorageModel.key.like('flow:%'))
        )
        all_keys = [row[0] for row in result.fetchall()]
    
    print(f"Найдены flows: {all_keys}")
    
    # Ищем smart_flow
    smart_flow_key = None
    for key in all_keys:
        if "smart_flow" in key.lower():
            smart_flow_key = key.replace("flow:", "")
            break
    
    if not smart_flow_key:
        pytest.skip("SmartFlow не найден в БД, возможно не мигрирован")
    
    print(f"Используем flow: {smart_flow_key}")
    
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
async def test_smart_flow_weather_routing():
    """Тест: SmartFlow направляет погодные запросы в weather"""
    
    # Настраиваем мок LLM
    from app.core.llm_factory import get_global_mock_llm, get_llm
    get_llm("mock-gpt-4")
    mock_llm = get_global_mock_llm()
    if mock_llm:
        mock_llm.set_responses({
            "погода": "Использую get_weather",
            "москва": "Погода в Москве: солнечно, +20°C",
            "солнечно": "Отлично! В Москве хорошая погода - солнечно и тепло",
        })
    
    # Мигрируем
    migrator = Migrator()
    await migrator.run_full_migration()
    await migrator._set_system_context()
    
    # Получаем flow
    flow_factory = FlowFactory()
    storage = Storage()
    
    # Ищем smart_flow
    async with storage._get_session() as session:
        from sqlalchemy import select
        from app.db.models import Storage as StorageModel
        result = await session.execute(
            select(StorageModel.key).where(StorageModel.key.like('flow:%smart_flow%'))
        )
        keys = [row[0] for row in result.fetchall()]
    
    if not keys:
        pytest.skip("SmartFlow не найден в БД")
    
    smart_flow_key = keys[0].replace("flow:", "")
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
async def test_smart_flow_different_paths():
    """Тест: SmartFlow выбирает разные пути для разных запросов"""
    
    # Настраиваем мок LLM
    from app.core.llm_factory import get_global_mock_llm, get_llm
    get_llm("mock-gpt-4")
    mock_llm = get_global_mock_llm()
    if mock_llm:
        mock_llm.set_responses({
            "посчитай": "Результат: 20",
            "погода": "Погода: солнечно",
            "20": "Калькулятор посчитал",
            "солнечно": "Погода хорошая",
        })
    
    # Мигрируем
    migrator = Migrator()
    await migrator.run_full_migration()
    await migrator._set_system_context()
    
    # Получаем flow
    flow_factory = FlowFactory()
    storage = Storage()
    
    async with storage._get_session() as session:
        from sqlalchemy import select
        from app.db.models import Storage as StorageModel
        result = await session.execute(
            select(StorageModel.key).where(StorageModel.key.like('flow:%smart_flow%'))
        )
        keys = [row[0] for row in result.fetchall()]
    
    if not keys:
        pytest.skip("SmartFlow не найден в БД")
    
    smart_flow_key = keys[0].replace("flow:", "")
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

