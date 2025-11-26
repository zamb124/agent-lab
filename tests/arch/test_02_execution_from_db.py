"""
Тест 2: Выполнение флоу из БД.

Проверяет что оба флоу (weather_flow и smart_flow) правильно выполняются
из БД конфигурации без обращения к исходному коду.
"""
import pytest
from langchain_core.messages import HumanMessage

# Таймаут для каждого теста (30 секунд)
pytestmark = pytest.mark.timeout(30)

@pytest.mark.asyncio
async def test_weather_flow_execution(migrated_db, flow_factory, system_context, unique_id, mock_llm):
    """Тест выполнения weather_flow из БД"""
    
    from apps.agents.agents.base import AgentInterrupt
    
    # Настраиваем mock_llm ДО создания flow
    from core.clients.llm import get_llm, get_global_mock_llm
    
    # Создаем мок если его еще нет
    _ = get_llm("mock-gpt-4")
    
    # Получаем и настраиваем мок
    global_mock = get_global_mock_llm("mock-gpt-4")
    if global_mock:
        global_mock.reset_call_counts()
        global_mock.configure(
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
    
    weather_flow = await flow_factory.get_flow("apps.agents.flows.weather_flow.weather_flow_config")
    
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
    
    # Настраиваем mock_llm ДО создания flow
    from core.clients.llm import get_llm, get_global_mock_llm
    
    # Создаем мок если его еще нет
    _ = get_llm("mock-gpt-4")
    
    # Получаем и настраиваем мок
    global_mock = get_global_mock_llm("mock-gpt-4")
    if global_mock:
        global_mock.reset_call_counts()
        global_mock.configure(
            tool_responses={
                "посчитай 7*8": {"tool": "calculate", "args": {"expression": "7*8"}},
                "7*8": {"tool": "calculate", "args": {"expression": "7*8"}},
            },
            responses={
                "посчитай 7*8": "Я выполню вычисление 7*8 = 56 используя калькулятор.",
                "7*8": "Результат вычисления 7*8 равен 56.",
                "calculate": "Результат вычисления 7*8 равен 56.",
                "56": "Результат вычисления: 56.",
                "исходный вопрос": "Пользователь спросил про вычисление 7*8, результат: 56",
                "калькулятор": "Калькулятор выполнил вычисление и получил результат 56.",
                "объясни": "Я объясню что произошло: пользователь попросил посчитать 7*8, калькулятор выполнил вычисление и получил результат 56.",
                "резюме": "Резюме: пользователь спросил про вычисление 7*8, калькулятор дал ответ 56.",
                "объясни что произошло": "Пользователь попросил посчитать 7*8. Калькулятор выполнил вычисление и получил результат 56.",
                "дай резюме": "Резюме: пользователь спросил про вычисление 7*8, калькулятор дал ответ 56."
            },
            default_response="Результат вычисления: 56."
        )
    
    smart_flow = await flow_factory.get_flow("apps.agents.flows.smart_flow.smart_flow_config")
    
    thread_id = unique_id("test_math")
    print(f"🔍 ТЕСТ: запускаем smart_flow с thread_id={thread_id}")
    print(f"🔍 ТЕСТ: MockLLM настроен: tool_responses={list(global_mock._tool_responses.keys()) if global_mock else 'None'}")
    print(f"🔍 ТЕСТ: MockLLM настроен: responses keys={list(global_mock._responses.keys()) if global_mock else 'None'}")
    
    result = await smart_flow.ainvoke(
        {"messages": [HumanMessage(content="Посчитай 7*8")]},
        config={"configurable": {"thread_id": thread_id}}
    )
    
    print(f"🔍 ТЕСТ: smart_flow завершен, получен результат")
    
    print(f"🔍 РЕЗУЛЬТАТ: {result}")
    store = result.get("store", {})
    print(f"🔍 original_question: {store.get('original_question', 'НЕТ')}")
    print(f"🔍 selected_agent: {store.get('selected_agent', 'НЕТ')}")
    print(f"🔍 final_message: {result['messages'][-1].content}")
    
    assert "messages" in result
    assert "store" in result
    assert "original_question" in store
    assert "selected_agent" in store
    # Проверяем что selected_agent это calculator (может быть "calculator" или "apps.agents.agents.calculator.agent.CalculatorAgent")
    assert store["selected_agent"] in ["calculator", "apps.agents.agents.calculator.agent.CalculatorAgent"], \
        f"selected_agent должен быть calculator, получено: {store['selected_agent']}"
    
    final_message = result["messages"][-1].content
    assert "56" in final_message or "7*8" in final_message
    
    print(f"✅ Smart flow математический тест из БД: {final_message[:100]}...")

@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_smart_flow_weather_execution(migrated_db, flow_factory, system_context, mock_llm, unique_id):
    """Тест погодного запроса в smart_flow из БД"""
    
    # Настраиваем mock_llm ДО создания flow
    from core.clients.llm import get_llm, get_global_mock_llm
    
    # Создаем мок если его еще нет
    _ = get_llm("mock-gpt-4")
    
    # Получаем и настраиваем мок
    global_mock = get_global_mock_llm("mock-gpt-4")
    if global_mock:
        global_mock.reset_call_counts()
        global_mock.configure(
            tool_responses={
                "какая погода": {"tool": "weather_agent_tool", "args": {"request": "Какая погода в Питере?"}},
            },
            responses={
                "какая погода": "Я проверю погоду в Питере используя инструмент get_weather.",
                "погода в питере": "Погода в Питере: +3°C, дождь",
            },
            default_response="Погода в Питере: +3°C, дождь"
        )
    
    smart_flow = await flow_factory.get_flow("apps.agents.flows.smart_flow.smart_flow_config")
    
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
@pytest.mark.timeout(60)
async def test_flow_isolation(migrated_db, flow_factory, system_context, mock_llm):
    """Тест изоляции флоу - разные thread_id не должны влиять друг на друга"""
    
    import asyncio
    
    # Настраиваем mock_llm ДО создания агентов
    from core.clients.llm import get_llm, get_global_mock_llm
    
    # Создаем мок если его еще нет
    _ = get_llm("mock-gpt-4")
    
    # Получаем и настраиваем мок
    global_mock = get_global_mock_llm("mock-gpt-4")
    if global_mock:
        global_mock.reset_call_counts()
        global_mock.configure(
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
    from apps.agents.container import get_agents_container
    agent_factory = get_agents_container().agent_factory
    
    from apps.agents.models import LLMConfig
    
    calculator_agent = await agent_factory.get_agent("apps.agents.agents.calculator.agent.CalculatorAgent")
    if calculator_agent and calculator_agent.config:
        if not calculator_agent.config.llm_config:
            calculator_agent.config.llm_config = LLMConfig(model="mock-gpt-4", context_window=8192)
        else:
            calculator_agent.config.llm_config.context_window = 8192
        await agent_factory.agent_repository.set(calculator_agent.config)
    
    explainer_agent = await agent_factory.get_agent("apps.agents.agents.explainer.agent.ExplainerAgent")
    if explainer_agent and explainer_agent.config and explainer_agent.config.llm_config:
        explainer_agent.config.llm_config.context_window = 8192
    
    smart_flow = await flow_factory.get_flow("apps.agents.flows.smart_flow.smart_flow_config")
    
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
        messages = result.get("messages", [])
        assert len(messages) > 0, f"Результат {i} должен содержать сообщения"
        message_content = " ".join([m.content if hasattr(m, 'content') else str(m) for m in messages])
        assert "4" in message_content or "2+2" in message_content or "четыре" in message_content.lower(), \
            f"Результат {i} не содержит правильный ответ: {message_content}"
    
    print("✅ Изоляция флоу работает корректно")
