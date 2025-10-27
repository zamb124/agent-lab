"""
Тест 2: Выполнение флоу из БД.

Проверяет что оба флоу (weather_flow и smart_flow) правильно выполняются
из БД конфигурации без обращения к исходному коду.
"""
import pytest
from langchain_core.messages import HumanMessage

@pytest.mark.asyncio
async def test_weather_flow_execution(migrated_db, flow_factory, unique_id):
    """Тест выполнения weather_flow из БД"""
    
    weather_flow = await flow_factory.get_flow("app.flows.weather_flow.weather_flow_config")
    
    result = await weather_flow.ainvoke(
        {"messages": [HumanMessage(content="Какая погода в Москве?")]},
        config={"configurable": {"thread_id": unique_id("test_weather")}}
    )
    
    assert "messages" in result
    assert len(result["messages"]) > 0
    
    final_message = result["messages"][-1].content
    assert isinstance(final_message, str)
    assert len(final_message) > 0
    
    print(f"✅ Weather flow выполнен из БД: {final_message[:100]}...")

@pytest.mark.asyncio
async def test_smart_flow_math_execution(migrated_db, flow_factory, mock_llm, unique_id):
    """Тест математического запроса в smart_flow из БД"""
    
    mock_llm.configure(
        responses={
            "посчитай 7*8": "Я выполню вычисление 7*8 = 56 используя калькулятор.",
            "7*8": "Результат вычисления 7*8 равен 56.",
            "исходный вопрос": "Пользователь спросил про вычисление 7*8, результат: 56",
            "калькулятор": "Калькулятор выполнил вычисление и получил результат 56."
        }
    )
    
    smart_flow = await flow_factory.get_flow("app.flows.smart_flow.smart_flow_config")
    
    result = await smart_flow.ainvoke(
        {"messages": [HumanMessage(content="Посчитай 7*8")]},
        config={"configurable": {"thread_id": unique_id("test_math")}}
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
async def test_smart_flow_weather_execution(migrated_db, flow_factory, unique_id):
    """Тест погодного запроса в smart_flow из БД"""
    
    smart_flow = await flow_factory.get_flow("app.flows.smart_flow.smart_flow_config")
    
    result = await smart_flow.ainvoke(
        {"messages": [HumanMessage(content="Какая погода в Питере?")]},
        config={"configurable": {"thread_id": unique_id("test_smart_weather")}}
    )
    
    assert "messages" in result
    assert "original_question" in result
    assert "selected_agent" in result
    assert result["selected_agent"] == "weather"
    
    final_message = result["messages"][-1].content
    assert len(final_message) > 0
    
    print(f"✅ Smart flow погодный тест из БД: {final_message[:100]}...")

@pytest.mark.asyncio
async def test_flow_isolation(migrated_db, flow_factory, mock_llm):
    """Тест изоляции флоу - разные thread_id не должны влиять друг на друга"""
    
    import asyncio
    
    mock_llm.configure(
        responses={
            "посчитай 2+2": "Я выполню вычисление 2+2 = 4 используя калькулятор.",
            "2+2": "Результат вычисления 2+2 равен 4.",
            "исходный вопрос": "Пользователь спросил про вычисление 2+2, результат: 4",
            "калькулятор": "Калькулятор выполнил вычисление и получил результат 4."
        }
    )
    
    smart_flow = await flow_factory.get_flow("app.flows.smart_flow.smart_flow_config")
    
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
