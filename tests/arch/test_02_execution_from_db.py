"""
Тест 2: Выполнение флоу из БД.

Проверяет что оба флоу (weather_flow и smart_flow) правильно выполняются
из БД конфигурации без обращения к исходному коду.
"""
import pytest
from langchain_core.messages import HumanMessage

@pytest.mark.asyncio
async def test_weather_flow_execution(migrated_db, flow_factory, system_context, unique_id, mock_llm):
    """Тест выполнения weather_flow из БД"""
    
    from app.agents.base import AgentInterrupt
    from app.core.container import get_container
    
    mock_llm.reset_call_counts()
    mock_llm.configure(
        tool_responses={
            "какая погода": {"tool": "get_weather", "args": {"city": "Москва"}},
            "погода в москве": {"tool": "get_weather", "args": {"city": "Москва"}},
        },
        responses={
            "погода": "Я проверю погоду в Москве используя инструмент get_weather.",
            "москва": "Я проверю погоду в Москве используя инструмент get_weather.",
            "какая погода": "Я проверю погоду в Москве используя инструмент get_weather.",
        },
        default_response="Погода в Москве: +5°C, облачно"
    )
    
    weather_flow = await flow_factory.get_flow("app.flows.weather_flow.weather_flow_config")
    
    if not weather_flow.entry_agent:
        await weather_flow.initialize()
    
    if weather_flow.entry_agent and weather_flow.entry_agent.config and weather_flow.entry_agent.config.llm_config:
        weather_flow.entry_agent.config.llm_config.context_window = 8192
    
    try:
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
    except AgentInterrupt as interrupt:
        pytest.fail(f"Неожиданный interrupt в тесте: {interrupt.value}")

@pytest.mark.asyncio
async def test_smart_flow_math_execution(migrated_db, flow_factory, system_context, mock_llm, unique_id):
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
    store = result.get("store", {})
    print(f"🔍 original_question: {store.get('original_question', 'НЕТ')}")
    print(f"🔍 selected_agent: {store.get('selected_agent', 'НЕТ')}")
    print(f"🔍 final_message: {result['messages'][-1].content}")
    
    assert "messages" in result
    assert "store" in result
    assert "original_question" in store
    assert "selected_agent" in store
    assert store["selected_agent"] == "calculator"
    
    final_message = result["messages"][-1].content
    assert "56" in final_message or "7*8" in final_message
    
    print(f"✅ Smart flow математический тест из БД: {final_message[:100]}...")

@pytest.mark.asyncio
async def test_smart_flow_weather_execution(migrated_db, flow_factory, system_context, unique_id):
    """Тест погодного запроса в smart_flow из БД"""
    
    smart_flow = await flow_factory.get_flow("app.flows.smart_flow.smart_flow_config")
    
    result = await smart_flow.ainvoke(
        {"messages": [HumanMessage(content="Какая погода в Питере?")]},
        config={"configurable": {"thread_id": unique_id("test_smart_weather")}}
    )
    
    assert "messages" in result
    store = result.get("store", {})
    assert "original_question" in store
    assert "selected_agent" in store
    assert store["selected_agent"] == "weather"
    
    final_message = result["messages"][-1].content
    assert len(final_message) > 0
    
    print(f"✅ Smart flow погодный тест из БД: {final_message[:100]}...")

@pytest.mark.asyncio
async def test_flow_isolation(migrated_db, flow_factory, system_context, mock_llm):
    """Тест изоляции флоу - разные thread_id не должны влиять друг на друга"""
    
    import asyncio
    
    mock_llm.reset_call_counts()
    mock_llm.configure(
        tool_responses={
            "посчитай 2+2": {"tool": "calculator_agent_tool", "args": {"request": "Посчитай 2+2"}},
        },
        responses={
            "посчитай 2+2": "Я выполню вычисление 2+2 = 4 используя калькулятор.",
            "2+2": "Результат вычисления 2+2 равен 4.",
            "исходный вопрос": "Пользователь спросил про вычисление 2+2, результат: 4",
            "калькулятор": "Калькулятор выполнил вычисление и получил результат 4."
        },
        default_response="Готово"
    )
    
    # Устанавливаем context_window для агентов, используемых в flow
    from app.core.container import get_container
    agent_factory = get_container().agent_factory
    
    calculator_agent = await agent_factory.get_agent("app.agents.calculator.agent.CalculatorAgent")
    if calculator_agent and calculator_agent.config and calculator_agent.config.llm_config:
        calculator_agent.config.llm_config.context_window = 8192
    
    explainer_agent = await agent_factory.get_agent("app.agents.explainer.agent.ExplainerAgent")
    if explainer_agent and explainer_agent.config and explainer_agent.config.llm_config:
        explainer_agent.config.llm_config.context_window = 8192
    
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
        store = result.get("store", {})
        assert store.get("selected_agent") == "calculator", f"Результат {i} неправильный: selected_agent={store.get('selected_agent')}"
        last_message = result["messages"][-1]
        message_content = last_message.content if hasattr(last_message, 'content') else str(last_message)
        assert "4" in message_content, f"Результат {i} не содержит правильный ответ: {message_content}"
    
    print("✅ Изоляция флоу работает корректно")
