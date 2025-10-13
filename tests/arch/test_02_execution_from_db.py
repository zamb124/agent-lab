"""
Тест 2: Выполнение флоу из БД.

Проверяет что оба флоу (weather_flow и smart_flow) правильно выполняются
из БД конфигурации без обращения к исходному коду.
"""
import pytest
import asyncio
from pathlib import Path
import sys

# Добавляем backend в путь
backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.core.flow_factory import FlowFactory
from langchain_core.messages import HumanMessage

@pytest.mark.asyncio
async def test_weather_flow_execution():
    """Тест выполнения weather_flow из БД"""
    
    # Миграция
    from app.core.migrator import Migrator
    migrator = Migrator()
    await migrator.run_full_migration()
    await migrator._set_system_context()
    
    flow_factory = FlowFactory()
    weather_flow = await flow_factory.get_flow("app.flows.weather_flow.weather_flow_config")
    
    # Тест погодного запроса
    import uuid
    result = await weather_flow.ainvoke(
        {"messages": [HumanMessage(content="Какая погода в Москве?")]},
        config={"configurable": {"thread_id": f"test_weather_{uuid.uuid4().hex[:8]}"}}
    )
    
    assert "messages" in result
    assert len(result["messages"]) > 0
    
    final_message = result["messages"][-1].content
    assert isinstance(final_message, str)
    assert len(final_message) > 0
    
    print(f"✅ Weather flow выполнен из БД: {final_message[:100]}...")

@pytest.mark.asyncio
async def test_smart_flow_math_execution():
    """Тест математического запроса в smart_flow из БД"""
    
    # Миграция
    from app.core.migrator import Migrator
    migrator = Migrator()
    await migrator.run_full_migration()
    await migrator._set_system_context()

    # Настраиваем мок для математических вычислений
    from app.core.llm_factory import get_global_mock_llm, get_llm
    
    get_llm("mock-gpt-4")
    
    mock_llm = get_global_mock_llm()
    if mock_llm:
        mock_llm.set_responses({
            "посчитай 7*8": "Я выполню вычисление 7*8 = 56 используя калькулятор.",
            "7*8": "Результат вычисления 7*8 равен 56.",
            "исходный вопрос": "Пользователь спросил про вычисление 7*8, результат: 56",
            "калькулятор": "Калькулятор выполнил вычисление и получил результат 56."
        })

    # Очищаем checkpointer перед тестом
    from app.core.checkpointer import get_checkpointer
    checkpointer = await get_checkpointer()
    
    flow_factory = FlowFactory()
    smart_flow = await flow_factory.get_flow("app.flows.smart_flow.smart_flow_config")
    
    # Тест математического запроса с чистым thread_id
    import uuid
    thread_id = f"test_math_{uuid.uuid4().hex[:8]}"
    
    # Очищаем состояние для этого thread_id
    try:
        await checkpointer.adelete({"configurable": {"thread_id": thread_id}})
    except:
        pass  # Игнорируем если состояния нет
    
    result = await smart_flow.ainvoke(
        {"messages": [HumanMessage(content="Посчитай 7*8")]},
        config={"configurable": {"thread_id": thread_id}}
    )
    
    print(f"🔍 РЕЗУЛЬТАТ: {result}")
    print(f"🔍 original_question: {result.get('original_question', 'НЕТ')}")
    print(f"🔍 selected_agent: {result.get('selected_agent', 'НЕТ')}")
    print(f"🔍 final_message: {result['messages'][-1].content}")
    
    assert "messages" in result
    assert "original_question" in result
    assert "selected_agent" in result
    assert result["selected_agent"] == "calculator"
    
    final_message = result["messages"][-1].content
    assert "56" in final_message or "7*8" in final_message
    
    print(f"✅ Smart flow математический тест из БД: {final_message[:100]}...")

@pytest.mark.asyncio
async def test_smart_flow_weather_execution():
    """Тест погодного запроса в smart_flow из БД"""
    
    # Миграция
    from app.core.migrator import Migrator
    migrator = Migrator()
    await migrator.run_full_migration()
    await migrator._set_system_context()
    
    flow_factory = FlowFactory()
    smart_flow = await flow_factory.get_flow("app.flows.smart_flow.smart_flow_config")
    
    # Тест погодного запроса
    import uuid
    result = await smart_flow.ainvoke(
        {"messages": [HumanMessage(content="Какая погода в Питере?")]},
        config={"configurable": {"thread_id": f"test_smart_weather_{uuid.uuid4().hex[:8]}"}}
    )
    
    assert "messages" in result
    assert "original_question" in result
    assert "selected_agent" in result
    assert result["selected_agent"] == "weather"
    
    final_message = result["messages"][-1].content
    assert len(final_message) > 0
    
    print(f"✅ Smart flow погодный тест из БД: {final_message[:100]}...")

@pytest.mark.asyncio
async def test_flow_isolation():
    """Тест изоляции флоу - разные thread_id не должны влиять друг на друга"""
    
    # Миграция
    from app.core.migrator import Migrator
    migrator = Migrator()
    await migrator.run_full_migration()
    await migrator._set_system_context()

    # Настраиваем мок для простых вычислений
    from app.core.llm_factory import get_global_mock_llm, get_llm
    
    get_llm("mock-gpt-4")
    
    mock_llm = get_global_mock_llm()
    if mock_llm:
        mock_llm.set_responses({
            "посчитай 2+2": "Я выполню вычисление 2+2 = 4 используя калькулятор.",
            "2+2": "Результат вычисления 2+2 равен 4.",
            "исходный вопрос": "Пользователь спросил про вычисление 2+2, результат: 4",
            "калькулятор": "Калькулятор выполнил вычисление и получил результат 4."
        })

    flow_factory = FlowFactory()
    smart_flow = await flow_factory.get_flow("app.flows.smart_flow.smart_flow_config")
    
    # Параллельные запросы с разными thread_id
    tasks = [
        smart_flow.ainvoke(
            {"messages": [HumanMessage(content="Посчитай 2+2")]},
            config={"configurable": {"thread_id": f"isolation_test_{i}"}}
        )
        for i in range(3)
    ]
    
    results = await asyncio.gather(*tasks)
    
    # Все результаты должны быть правильными
    for i, result in enumerate(results):
        assert result["selected_agent"] == "calculator", f"Результат {i} неправильный"
        assert "4" in result["messages"][-1].content, f"Результат {i} не содержит правильный ответ"
    
    print("✅ Изоляция флоу работает корректно")
