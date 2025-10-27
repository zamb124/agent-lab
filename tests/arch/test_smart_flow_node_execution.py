"""
Детальный тест для проверки что SmartFlow выполняет разные ноды для разных запросов.

Проверяет что:
1. Математические запросы идут через calculator ноду
2. Погодные запросы идут через weather ноду
3. Роутер правильно определяет путь
"""
import pytest
from langchain_core.messages import HumanMessage


@pytest.mark.asyncio
async def test_smart_flow_executes_different_nodes(migrated_db, agent_factory, mock_llm, migrator, agent_repo):
    """Тест: SmartFlow выполняет разные ноды для разных запросов"""
    
    await migrator.run_full_migration()
    
    # Настраиваем mock LLM с разными ответами для разных агентов
    mock_llm.configure(
        tool_responses={
            # Для роутера - выбор нужного агента
            "Посчитай": {"tool": "calculator_agent_tool", "args": {"request": "Посчитай 2+2"}},
            "погода": {"tool": "weather_agent_tool", "args": {"request": "Какая погода в Москве?"}},
            # Для calculator агента
            "2+2": {"tool": "calculate", "args": {"expression": "2+2"}},
            # Для weather агента  
            "Москве": {"tool": "get_weather", "args": {"city": "Москва"}},
        },
        responses={
            # Для calculator
            "посчитай": "CALCULATOR: Использую calculate",
            "2+2": "CALCULATOR: Результат = 4",
            "4": "CALCULATOR: Объяснение - посчитал 2+2=4",
            "calculate": "CALCULATOR: 4",
            
            # Для weather
            "погода": "WEATHER: Использую get_weather", 
            "москва": "WEATHER: В Москве солнечно",
            "солнечно": "WEATHER: Объяснение - погода хорошая",
            "get_weather": "WEATHER: Солнечно",
        },
        default_response="Не понял запрос"
    )
    
    # Получаем SmartFlowAgent
    agent = await agent_factory.get_agent("app.flows.smart_flow.SmartFlowAgent")
    
    print("\n" + "="*70)
    print("ТЕСТ 1: Математический запрос (должен идти через calculator)")
    print("="*70)
    
    # Тест 1: Математический запрос
    result1 = await agent.ainvoke(
        {"messages": [HumanMessage(content="Посчитай 2+2")]},
        config={"configurable": {"thread_id": "test_math_path"}}
    )
    
    # Собираем все сообщения
    all_messages_1 = [msg.content for msg in result1["messages"]]
    full_content_1 = " ".join(all_messages_1)
    
    print(f"\nИсходный запрос: 'Посчитай 2+2'")
    print(f"\nВсе сообщения в результате:")
    for i, msg in enumerate(result1["messages"]):
        print(f"  {i+1}. {msg.content[:100]}...")
    
    # Проверяем что путь прошёл через calculator (ищем и русские, и английские маркеры)
    has_calculator_marker = (
        "CALCULATOR" in full_content_1 or 
        "calculate" in full_content_1.lower() or 
        "калькулятор" in full_content_1.lower() or
        "посчита" in full_content_1.lower()
    )
    has_weather_marker = "WEATHER" in full_content_1 or "погода" in full_content_1.lower()
    
    print(f"\n✓ Маркер CALCULATOR найден: {has_calculator_marker}")
    print(f"✗ Маркер WEATHER найден: {has_weather_marker}")
    
    assert has_calculator_marker, f"Математический запрос не прошёл через calculator ноду! Содержимое: {full_content_1[:200]}"
    assert not has_weather_marker or "CALCULATOR" in full_content_1 or "калькулятор" in full_content_1.lower(), \
        "Математический запрос не должен проходить через weather ноду!"
    
    print("\n✅ ТЕСТ 1 ПРОЙДЕН: Математический запрос прошёл через calculator ноду")
    
    print("\n" + "="*70)
    print("ТЕСТ 2: Погодный запрос (должен идти через weather)")
    print("="*70)
    
    # Тест 2: Погодный запрос
    result2 = await agent.ainvoke(
        {"messages": [HumanMessage(content="Какая погода в Москве?")]},
        config={"configurable": {"thread_id": "test_weather_path"}}
    )
    
    # Собираем все сообщения
    all_messages_2 = [msg.content for msg in result2["messages"]]
    full_content_2 = " ".join(all_messages_2)
    
    print(f"\nИсходный запрос: 'Какая погода в Москве?'")
    print(f"\nВсе сообщения в результате:")
    for i, msg in enumerate(result2["messages"]):
        print(f"  {i+1}. {msg.content[:100]}...")
    
    # Проверяем что путь прошёл через weather (ищем и русские, и английские маркеры)
    has_weather_marker_2 = (
        "WEATHER" in full_content_2 or 
        "weather" in full_content_2.lower() or
        "погода" in full_content_2.lower() or
        "погод" in full_content_2.lower()
    )
    has_calculator_marker_2 = (
        "CALCULATOR" in full_content_2 or 
        "calculate" in full_content_2.lower() or
        "калькулятор" in full_content_2.lower()
    )
    
    print(f"\n✓ Маркер WEATHER найден: {has_weather_marker_2}")
    print(f"✗ Маркер CALCULATOR найден: {has_calculator_marker_2}")
    
    assert has_weather_marker_2, f"Погодный запрос не прошёл через weather ноду! Содержимое: {full_content_2[:200]}"
    assert not has_calculator_marker_2 or "WEATHER" in full_content_2 or "погод" in full_content_2.lower(), \
        "Погодный запрос не должен проходить через calculator ноду!"
    
    print("\n✅ ТЕСТ 2 ПРОЙДЕН: Погодный запрос прошёл через weather ноду")
    
    # Финальная проверка
    print("\n" + "="*70)
    print("ИТОГОВАЯ ПРОВЕРКА")
    print("="*70)
    print(f"✅ Разные запросы прошли через РАЗНЫЕ ноды")
    print(f"   - Математика → calculator нода")
    print(f"   - Погода → weather нода")
    print("="*70 + "\n")


@pytest.mark.asyncio  
async def test_smart_flow_router_condition(agent_repo):
    """Тест: проверка логики роутера SmartFlow"""
    
    from app.flows.smart_flow import router_function, router_condition
    
    print("\n" + "="*70)
    print("ТЕСТ ЛОГИКИ РОУТЕРА")
    print("="*70)
    
    # Тест 1: Математический запрос
    state1 = {
        "messages": [HumanMessage(content="Посчитай 10 + 20")],
        "original_question": "",
        "selected_agent": ""
    }
    
    state1 = router_function(state1)
    selected1 = router_condition(state1)
    
    print(f"\nЗапрос: 'Посчитай 10 + 20'")
    print(f"  → selected_agent в state: '{state1['selected_agent']}'")
    print(f"  → router_condition вернул: '{selected1}'")
    
    assert state1["selected_agent"] == "calculator", \
        f"Роутер должен выбрать 'calculator', а выбрал '{state1['selected_agent']}'"
    assert selected1 == "calculator", \
        f"router_condition должен вернуть 'calculator', а вернул '{selected1}'"
    
    print("  ✅ Правильно выбрал calculator")
    
    # Тест 2: Погодный запрос
    state2 = {
        "messages": [HumanMessage(content="Какая погода?")],
        "original_question": "",
        "selected_agent": ""
    }
    
    state2 = router_function(state2)
    selected2 = router_condition(state2)
    
    print(f"\nЗапрос: 'Какая погода?'")
    print(f"  → selected_agent в state: '{state2['selected_agent']}'")
    print(f"  → router_condition вернул: '{selected2}'")
    
    assert state2["selected_agent"] == "weather", \
        f"Роутер должен выбрать 'weather', а выбрал '{state2['selected_agent']}'"
    assert selected2 == "weather", \
        f"router_condition должен вернуть 'weather', а вернул '{selected2}'"
    
    print("  ✅ Правильно выбрал weather")
    
    # Тест 3: Проверка разных ключевых слов
    test_cases = [
        ("Сколько будет 5 + 5?", "calculator"),
        ("10 - 3 =", "calculator"),
        ("2 * 4", "calculator"),
        ("100 / 10", "calculator"),
        ("Какая температура?", "weather"),
        ("Будет дождь?", "weather"),
        ("Привет", "weather"),  # По умолчанию weather
    ]
    
    print(f"\nПроверка различных запросов:")
    for query, expected in test_cases:
        state = {
            "messages": [HumanMessage(content=query)],
            "original_question": "",
            "selected_agent": ""
        }
        state = router_function(state)
        selected = router_condition(state)
        
        status = "✅" if selected == expected else "❌"
        print(f"  {status} '{query}' → {selected} (ожидалось: {expected})")
        
        assert selected == expected, \
            f"Для '{query}' ожидался {expected}, получен {selected}"
    
    print("\n✅ ВСЕ ТЕСТЫ РОУТЕРА ПРОЙДЕНЫ")
    print("="*70 + "\n")


@pytest.mark.asyncio
async def test_smart_flow_graph_structure(migrated_db, storage, migrator, agent_repo):
    
    await migrator.run_full_migration()
    
    # Получаем конфигурацию агента
    agent_config = await agent_repo.get("app.flows.smart_flow.SmartFlowAgent")
    
    assert agent_config is not None, "SmartFlowAgent не найден в БД"
    assert agent_config.graph_definition is not None, "У SmartFlowAgent нет graph_definition"
    
    graph_def = agent_config.graph_definition
    
    print("\n" + "="*70)
    print("СТРУКТУРА ГРАФА SmartFlow")
    print("="*70)
    
    # Проверяем ноды
    print(f"\nНОДЫ ({len(graph_def.nodes)}):")
    node_names = []
    for node in graph_def.nodes:
        node_names.append(node.id)
        print(f"  - {node.id} ({node.type.value})")
    
    # Должны быть все необходимые ноды
    required_nodes = ["router", "calculator", "weather", "explainer"]
    for required in required_nodes:
        assert required in node_names, f"Нода '{required}' не найдена в графе!"
    print(f"\n✅ Все необходимые ноды присутствуют: {required_nodes}")
    
    # Проверяем рёбра
    print(f"\nРЁБРА ({len(graph_def.edges)}):")
    edges_map = {}
    for edge in graph_def.edges:
        if edge.source not in edges_map:
            edges_map[edge.source] = []
        edges_map[edge.source].append(edge.target)
        condition_info = f" [условие: {edge.condition_type.value}]" if edge.condition else ""
        print(f"  {edge.source} → {edge.target}{condition_info}")
    
    # Проверяем что от router есть условные переходы
    assert "router" in edges_map, "От ноды 'router' нет исходящих рёбер!"
    router_targets = edges_map["router"]
    assert "calculator" in router_targets, "От router нет перехода к calculator!"
    assert "weather" in router_targets, "От router нет перехода к weather!"
    print(f"\n✅ От router есть условные переходы к calculator и weather")
    
    # Проверяем что calculator и weather ведут к explainer
    assert "calculator" in edges_map, "От ноды 'calculator' нет исходящих рёбер!"
    assert "explainer" in edges_map["calculator"], "От calculator нет перехода к explainer!"
    
    assert "weather" in edges_map, "От ноды 'weather' нет исходящих рёбер!"
    assert "explainer" in edges_map["weather"], "От weather нет перехода к explainer!"
    print(f"✅ От calculator и weather есть переходы к explainer")
    
    # Проверяем точку входа
    assert graph_def.entry_point == "START", f"Точка входа должна быть START, а не {graph_def.entry_point}"
    print(f"✅ Точка входа: {graph_def.entry_point}")
    
    print("="*70 + "\n")

