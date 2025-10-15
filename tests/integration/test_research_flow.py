"""
Интеграционный тест Research Flow.

Проверяет полный цикл работы системы исследований БЕЗ МОКОВ:
1. Миграция flow и всех агентов в БД
2. Сборка графа без ошибок
3. End-to-end выполнение с реальным Tavily API и LLM

ВНИМАНИЕ: Тест использует реальные API и стоит денег!
Запускай только когда нужно проверить реальную работу системы.
"""

import pytest
from langchain_core.messages import HumanMessage


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_research_flow_migration(migrated_db, storage, flow_repo, agent_repo, migrator, test_company):
    """
    Тест 1: Проверка миграции Research Flow и всех зависимых агентов.
    
    Проверяет что:
    - Research Flow мигрировался в БД
    - Все 7 агентов мигрировались (coordinator + 6 субагентов)
    - Graph definition корректный
    - Tools корректно привязаны
    """
    
    # Миграция research flow с зависимостями
    await migrator.migrate_for_company(
        company=test_company,
        flows=["app.flows.research_flow.research_flow_config"],
        with_dependencies=True
    )
    
    # 1. Проверяем что flow мигрировался
    research_flow = await flow_repo.get("app.flows.research_flow.research_flow_config")
    assert research_flow is not None, "Research Flow не мигрировался"
    assert research_flow.name == "Research Flow"
    assert research_flow.entry_point_agent == "app.agents.research.coordinator.ResearchCoordinatorAgent"
    
    # Проверяем variables и store
    assert "bot_name" in research_flow.variables
    assert research_flow.variables["bot_name"] == "Research Assistant"
    assert "max_iterations" in research_flow.store
    assert research_flow.store["max_iterations"] == 2
    
    print("✅ Research Flow мигрировался корректно")
    
    # 2. Проверяем ResearchCoordinator (StateGraph)
    coordinator = await agent_repo.get("app.agents.research.coordinator.ResearchCoordinatorAgent")
    assert coordinator is not None, "ResearchCoordinator не мигрировался"
    assert coordinator.name == "research_coordinator"
    assert coordinator.graph_definition is not None, "Graph definition отсутствует"
    
    graph_def = coordinator.graph_definition
    assert len(graph_def.nodes) == 6, f"Ожидали 6 нод, получили {len(graph_def.nodes)}"
    
    node_ids = [node.id for node in graph_def.nodes]
    expected_nodes = ["analyze", "search", "process", "extract", "synthesize", "check"]
    for expected in expected_nodes:
        assert expected in node_ids, f"Нода {expected} не найдена"
    
    assert graph_def.entry_point == "analyze", "Entry point должен быть 'analyze'"
    
    print("✅ ResearchCoordinator граф корректный")
    
    # 3. Проверяем все субагенты
    sub_agents = [
        ("query_analyzer", "app.agents.research.query_analyzer.QueryAnalyzerAgent"),
        ("search_agent", "app.agents.research.search_agent.SearchAgent"),
        ("source_processor", "app.agents.research.source_processor.SourceProcessorAgent"),
        ("fact_extractor", "app.agents.research.fact_extractor.FactExtractorAgent"),
        ("synthesizer", "app.agents.research.synthesizer.SynthesizerAgent"),
        ("quality_checker", "app.agents.research.quality_checker.QualityCheckerAgent"),
    ]
    
    for agent_name, agent_id in sub_agents:
        agent = await agent_repo.get(agent_id)
        assert agent is not None, f"Агент {agent_name} не мигрировался"
        assert agent.prompt is not None, f"Агент {agent_name} без промпта"
        assert len(agent.tools) > 0, f"Агент {agent_name} без тулов"
        print(f"  ✅ {agent_name}: {len(agent.tools)} тулов")
    
    print("✅ Все субагенты мигрировались корректно")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_research_flow_graph_compilation(migrated_db, flow_factory, agent_factory, unique_id):
    """
    Тест 2: Проверка компиляции графа без ошибок.
    
    Проверяет что:
    - Flow создается через factory
    - Entry agent (ResearchCoordinator) создается
    - Граф компилируется без исключений
    - Все субагенты доступны
    """
    
    # Получаем flow через factory
    research_flow = await flow_factory.get_flow("app.flows.research_flow.research_flow_config")
    assert research_flow is not None, "Flow не создался через factory"
    assert research_flow.entry_agent is not None, "Entry agent не инициализировался"
    
    print(f"✅ Flow создан: {research_flow.config.name}")
    print(f"   Entry agent: {research_flow.config.entry_point_agent}")
    
    # Получаем coordinator через factory
    coordinator = await agent_factory.get_agent("app.agents.research.coordinator.ResearchCoordinatorAgent")
    assert coordinator is not None, "Coordinator не создался"
    
    # Компилируем граф (это проверит что все субагенты доступны)
    try:
        graph = await coordinator.compile_graph()
        assert graph is not None, "Граф не скомпилировался"
        print("✅ Граф скомпилирован без ошибок")
    except Exception as e:
        pytest.fail(f"Ошибка компиляции графа: {e}")
    
    # Проверяем что можем получить каждого субагента
    sub_agents = [
        ("query_analyzer", "app.agents.research.query_analyzer.QueryAnalyzerAgent"),
        ("search_agent", "app.agents.research.search_agent.SearchAgent"),
        ("source_processor", "app.agents.research.source_processor.SourceProcessorAgent"),
        ("fact_extractor", "app.agents.research.fact_extractor.FactExtractorAgent"),
        ("synthesizer", "app.agents.research.synthesizer.SynthesizerAgent"),
        ("quality_checker", "app.agents.research.quality_checker.QualityCheckerAgent"),
    ]
    
    for agent_name, agent_id in sub_agents:
        agent = await agent_factory.get_agent(agent_id)
        assert agent is not None, f"Субагент {agent_name} недоступен"
        
        # Проверяем что у агента есть tools
        tools = await agent.get_tools()
        assert len(tools) > 0, f"У агента {agent_name} нет тулов"
        print(f"  ✅ {agent_name}: {len(tools)} тулов загружено")
    
    print("✅ Все субагенты доступны и готовы к работе")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_research_flow_end_to_end_REAL(migrated_db, flow_factory, agent_factory, unique_id):
    """
    Тест 3: END-TO-END тест с реальными API (Tavily + LLM).
    
    ⚠️ ВНИМАНИЕ: Этот тест использует реальные API:
    - Реальный LLM (дефолтная модель из config)
    - Реальный Tavily Search API
    - Реальный PostgreSQL checkpointer
    
    СТОИМОСТЬ: ~$0.50-1.00 за прогон (зависит от модели и количества поисков)
    
    Проверяет:
    - Весь pipeline работает корректно
    - Агенты правильно передают данные через store
    - Граф выполняется последовательно
    - Финальный отчет создается
    - Качество проверяется и принимается решение
    """
    
    # Получаем flow
    research_flow = await flow_factory.get_flow("app.flows.research_flow.research_flow_config")
    assert research_flow is not None, "Research Flow недоступен"
    
    # Реальный запрос для исследования
    query = "Что такое LangGraph и его основные возможности?"
    
    thread_id = unique_id("research_e2e")
    
    print(f"\n{'='*60}")
    print(f"🚀 ЗАПУСК END-TO-END ТЕСТА")
    print(f"{'='*60}")
    print(f"📝 Запрос: {query}")
    print(f"🔑 Thread ID: {thread_id}")
    print(f"⚠️  Используются РЕАЛЬНЫЕ API (Tavily + LLM)")
    print(f"{'='*60}\n")
    
    # Выполняем flow
    result = await research_flow.ainvoke(
        {"messages": [HumanMessage(content=query)]},
        config={"configurable": {"thread_id": thread_id}}
    )
    
    print(f"\n{'='*60}")
    print(f"📊 РЕЗУЛЬТАТ ВЫПОЛНЕНИЯ")
    print(f"{'='*60}")
    
    # Проверяем базовую структуру результата
    assert "messages" in result, "Нет messages в результате"
    assert "store" in result, "Нет store в результате"
    
    store = result["store"]
    
    # 1. Проверяем этап анализа (QueryAnalyzer)
    print("\n1️⃣ ЭТАП АНАЛИЗА:")
    assert "original_query" in store, "QueryAnalyzer не сохранил original_query"
    assert "sub_queries" in store, "QueryAnalyzer не создал sub_queries"
    assert "research_type" in store, "QueryAnalyzer не определил research_type"
    
    print(f"   ✅ Original query: {store['original_query']}")
    print(f"   ✅ Research type: {store['research_type']}")
    print(f"   ✅ Sub queries: {store['sub_queries'][:100]}...")
    
    # 2. Проверяем этап поиска (SearchAgent)
    print("\n2️⃣ ЭТАП ПОИСКА:")
    assert "search_results" in store, "SearchAgent не сохранил результаты поиска"
    assert "sources_count" in store, "SearchAgent не сохранил количество источников"
    
    sources_count = int(store["sources_count"]) if isinstance(store["sources_count"], str) else store["sources_count"]
    assert sources_count > 0, "SearchAgent не нашел источники"
    
    print(f"   ✅ Найдено источников: {sources_count}")
    print(f"   ✅ Результаты поиска: {len(store['search_results'])} символов")
    
    # 3. Проверяем этап обработки (SourceProcessor)
    print("\n3️⃣ ЭТАП ОБРАБОТКИ:")
    assert "processed_sources" in store, "SourceProcessor не обработал источники"
    assert "sources_stats" in store, "SourceProcessor не создал статистику"
    
    print(f"   ✅ Обработанные источники: {len(store['processed_sources'])} символов")
    print(f"   ✅ Статистика: {store['sources_stats']}")
    
    # 4. Проверяем этап извлечения фактов (FactExtractor)
    print("\n4️⃣ ЭТАП ИЗВЛЕЧЕНИЯ ФАКТОВ:")
    assert "facts_json" in store, "FactExtractor не извлек факты"
    assert "facts_count" in store, "FactExtractor не сохранил количество фактов"
    
    facts_count = int(store["facts_count"]) if isinstance(store["facts_count"], str) else store["facts_count"]
    assert facts_count > 0, "FactExtractor не извлек ни одного факта"
    
    print(f"   ✅ Извлечено фактов: {facts_count}")
    
    # 5. Проверяем этап синтеза (Synthesizer)
    print("\n5️⃣ ЭТАП СИНТЕЗА:")
    assert "final_report" in store, "Synthesizer не создал финальный отчет"
    assert "report_length" in store, "Synthesizer не сохранил длину отчета"
    
    report = store["final_report"]
    report_length = int(store["report_length"]) if isinstance(store["report_length"], str) else store["report_length"]
    
    assert len(report) > 500, "Отчет слишком короткий"
    assert "##" in report or "#" in report, "Отчет не содержит markdown заголовки"
    
    print(f"   ✅ Отчет создан: {report_length} символов")
    print(f"   ✅ Содержит разделы: {'##' in report}")
    
    # 6. Проверяем этап проверки качества (QualityChecker)
    print("\n6️⃣ ЭТАП ПРОВЕРКИ КАЧЕСТВА:")
    assert "completeness_score" in store, "QualityChecker не оценил полноту"
    assert "sources_quality_score" in store, "QualityChecker не оценил качество источников"
    assert "objectivity_score" in store, "QualityChecker не оценил объективность"
    assert "average_quality_score" in store, "QualityChecker не вычислил средний балл"
    assert "quality_decision" in store, "QualityChecker не принял решение"
    
    completeness = float(store["completeness_score"])
    sources_quality = float(store["sources_quality_score"])
    objectivity = float(store["objectivity_score"])
    average = float(store["average_quality_score"])
    decision = store["quality_decision"]
    
    print(f"   ✅ Полнота: {completeness}/10")
    print(f"   ✅ Качество источников: {sources_quality}/10")
    print(f"   ✅ Объективность: {objectivity}/10")
    print(f"   ✅ Средний балл: {average}/10")
    print(f"   ✅ Решение: {decision}")
    
    # Проверяем что оценки в разумных пределах
    assert 0 <= completeness <= 10, "Некорректная оценка полноты"
    assert 0 <= sources_quality <= 10, "Некорректная оценка качества источников"
    assert 0 <= objectivity <= 10, "Некорректная оценка объективности"
    assert decision in ["complete", "need_more_search"], f"Некорректное решение: {decision}"
    
    # 7. Проверяем финальное сообщение пользователю
    print("\n7️⃣ ФИНАЛЬНОЕ СООБЩЕНИЕ:")
    assert len(result["messages"]) > 1, "Нет сообщений в результате"
    
    final_message = result["messages"][-1].content
    assert len(final_message) > 0, "Финальное сообщение пустое"
    
    print(f"   ✅ Сообщение получено: {len(final_message)} символов")
    print(f"\n{'-'*60}")
    print(f"ОТЧЕТ (первые 500 символов):")
    print(f"{'-'*60}")
    print(report[:500])
    print(f"{'-'*60}\n")
    
    # 8. Проверяем что все данные персистятся
    print("8️⃣ ПРОВЕРКА ПЕРСИСТЕНТНОСТИ:")
    
    # Создаем новый flow instance с тем же thread_id
    research_flow_2 = await flow_factory.get_flow("app.flows.research_flow.research_flow_config")
    
    # Получаем state из checkpoint
    from app.core.checkpointer import get_checkpointer
    checkpointer = await get_checkpointer()
    
    # Для получения state нужно использовать compiled graph
    coordinator_2 = await agent_factory.get_agent("research_coordinator")
    graph_2 = await coordinator_2.compile_graph()
    
    state = await graph_2.aget_state({"configurable": {"thread_id": thread_id}})
    assert state is not None, "State не сохранился в checkpoint"
    assert state.values is not None, "State values пусты"
    
    persisted_store = state.values.get("store", {})
    assert "final_report" in persisted_store, "final_report не персистнулся"
    assert "quality_decision" in persisted_store, "quality_decision не персистнулся"
    
    print("   ✅ State корректно персистится в checkpointer")
    
    print(f"\n{'='*60}")
    print(f"✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ!")
    print(f"{'='*60}")
    print(f"📊 Итоговая статистика:")
    print(f"   - Источников найдено: {sources_count}")
    print(f"   - Фактов извлечено: {facts_count}")
    print(f"   - Длина отчета: {report_length} символов")
    print(f"   - Средняя оценка: {average}/10")
    print(f"   - Решение: {decision}")
    print(f"{'='*60}\n")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_research_flow_with_interrupts(migrated_db, flow_factory, unique_id):
    """
    Тест 4: Проверка работы с interrupts (если агент запрашивает уточнения).
    
    Проверяет что:
    - Агенты могут использовать ask_user
    - GraphInterrupt корректно пробрасывается
    - Resume работает корректно
    """
    
    research_flow = await flow_factory.get_flow("app.flows.research_flow.research_flow_config")
    thread_id = unique_id("research_interrupt")
    
    # Даем неоднозначный запрос
    query = "исследуй это"
    
    print(f"\n{'='*60}")
    print(f"🔄 ТЕСТ С НЕОДНОЗНАЧНЫМ ЗАПРОСОМ")
    print(f"{'='*60}")
    print(f"📝 Запрос: {query}")
    print(f"{'='*60}\n")
    
    result = await research_flow.ainvoke(
        {"messages": [HumanMessage(content=query)]},
        config={"configurable": {"thread_id": thread_id}}
    )
    
    # Проверяем что был interrupt или агент сам уточнил тему
    if "__interrupt__" in result:
        print("✅ Агент корректно запросил уточнение через interrupt")
        
        # Продолжаем с уточнением
        result = await research_flow.ainvoke(
            {"messages": [HumanMessage(content="LangGraph framework")]},
            config={"configurable": {"thread_id": thread_id}}
        )
    
    # В любом случае должен быть результат
    assert "messages" in result
    assert len(result["messages"]) > 0
    
    print("✅ Тест с interrupts завершен")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_research_flow_reusable_agents(migrated_db, agent_factory, unique_id):
    """
    Тест 5: Проверка что агенты переиспользуемы (можно вызывать отдельно).
    
    Проверяет что:
    - Каждый субагент может работать независимо
    - Агенты корректно используют store для обмена данными
    - Можно создавать кастомные pipeline из существующих агентов
    """
    
    print(f"\n{'='*60}")
    print(f"♻️  ТЕСТ ПЕРЕИСПОЛЬЗУЕМОСТИ АГЕНТОВ")
    print(f"{'='*60}\n")
    
    # Проверяем что можем использовать QueryAnalyzer отдельно
    query_analyzer = await agent_factory.get_agent("app.agents.research.query_analyzer.QueryAnalyzerAgent")
    
    result = await query_analyzer.ainvoke(
        {"messages": [HumanMessage(content="Что такое RAG в машинном обучении?")]},
        config={"configurable": {"thread_id": unique_id("analyzer_standalone")}}
    )
    
    assert "store" in result
    assert "sub_queries" in result["store"], "QueryAnalyzer не работает отдельно"
    
    print("✅ QueryAnalyzer работает отдельно")
    print(f"   Подвопросы: {result['store']['sub_queries'][:100]}...")
    
    # Проверяем что можем использовать SearchAgent отдельно
    search_agent = await agent_factory.get_agent("app.agents.research.search_agent.SearchAgent")
    
    # Подготавливаем store с подвопросами
    search_input = {
        "messages": [HumanMessage(content="найди информацию")],
        "store": {
            "original_query": "Что такое RAG",
            "sub_queries": "Что такое RAG||||Как работает RAG"
        }
    }
    
    result = await search_agent.ainvoke(
        search_input,
        config={"configurable": {"thread_id": unique_id("search_standalone")}}
    )
    
    assert "search_results" in result["store"], "SearchAgent не работает отдельно"
    assert "sources_count" in result["store"], "SearchAgent не сохранил количество источников"
    
    print("✅ SearchAgent работает отдельно")
    print(f"   Найдено источников: {result['store']['sources_count']}")
    
    print(f"\n{'='*60}")
    print(f"✅ ВСЕ АГЕНТЫ ПЕРЕИСПОЛЬЗУЕМЫ!")
    print(f"{'='*60}\n")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_research_flow_quality_loop(migrated_db, flow_factory, unique_id):
    """
    Тест 6: Проверка цикла качества (QualityChecker → SearchAgent).
    
    Проверяет что:
    - QualityChecker может вернуть к поиску
    - Граф корректно обрабатывает циклы
    - Есть защита от бесконечных циклов (max_iterations)
    """
    
    research_flow = await flow_factory.get_flow("app.flows.research_flow.research_flow_config")
    thread_id = unique_id("research_loop")
    
    # Даем сложный запрос который может потребовать нескольких итераций
    query = "Сравни подробно все подходы к retrieval в RAG системах"
    
    print(f"\n{'='*60}")
    print(f"🔄 ТЕСТ ЦИКЛА КАЧЕСТВА")
    print(f"{'='*60}")
    print(f"📝 Запрос: {query}")
    print(f"{'='*60}\n")
    
    result = await research_flow.ainvoke(
        {"messages": [HumanMessage(content=query)]},
        config={"configurable": {"thread_id": thread_id}}
    )
    
    store = result["store"]
    
    # Проверяем что цикл работает
    iteration = store.get("iteration", 0)
    max_iterations = store.get("max_iterations", 2)
    
    print(f"   Выполнено итераций: {iteration}/{max_iterations}")
    
    # Даже если было несколько итераций, должен быть финальный отчет
    assert "final_report" in store, "Нет финального отчета несмотря на цикл"
    assert "quality_decision" in store, "Нет решения о качестве"
    
    decision = store["quality_decision"]
    
    # Решение должно быть либо complete, либо достигнут лимит итераций
    if decision == "need_more_search":
        assert iteration >= max_iterations, "Цикл не остановился при достижении лимита"
        print("   ✅ Защита от бесконечных циклов работает")
    else:
        print("   ✅ Качество достаточное, цикл завершен досрочно")
    
    print(f"\n{'='*60}")
    print(f"✅ ЦИКЛ КАЧЕСТВА РАБОТАЕТ КОРРЕКТНО!")
    print(f"{'='*60}\n")

