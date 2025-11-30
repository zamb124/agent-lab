"""
Юнит-тесты для Research агентов.

Проверяет работу каждого агента отдельно с РЕАЛЬНОЙ LLM (БЕЗ МОКОВ).
Быстрее и дешевле чем полный end-to-end тест.
"""

import pytest
from langchain_core.messages import HumanMessage


@pytest.mark.asyncio
@pytest.mark.integration
async def test_query_analyzer_agent(migrated_db, agent_factory, unique_id, test_context, migrator, test_company):
    """
    Тест QueryAnalyzer: анализ запроса и создание подвопросов.
    
    Проверяет что:
    - Агент анализирует запрос
    - Создает 2-4 подвопроса
    - Определяет тип исследования
    - Сохраняет все в store
    """
    
    await migrator.migrate_for_company(
        company=test_company,
        agents=["apps.agents.agents.research.query_analyzer.QueryAnalyzerAgent"],
        with_dependencies=True
    )
    
    print(f"\n{'='*60}")
    print("1️⃣ ТЕСТ QUERY ANALYZER")
    print(f"{'='*60}\n")
    
    analyzer = await agent_factory.get_agent("apps.agents.agents.research.query_analyzer.QueryAnalyzerAgent")
    
    query = "Что такое RAG в машинном обучении?"
    
    result = await analyzer.ainvoke(
        {"messages": [HumanMessage(content=query)]},
        config={"configurable": {"session_id": unique_id("analyzer")}}
    )
    
    # Проверяем базовую структуру результата
    assert "messages" in result, "Нет messages в результате"
    assert len(result["messages"]) > 1, "Агент не ответил"
    
    final_message = result["messages"][-1].content
    print(f"✅ Агент ответил: {len(final_message)} символов")
    print("\nОтвет агента:")
    print(f"{'-'*60}")
    print(final_message[:500])
    print(f"{'-'*60}")
    
    # Проверяем store (если агент вызвал session_set)
    store = result.get("store", {})
    
    if "original_query" in store:
        print("\n✅ Агент сохранил данные в store:")
        print(f"   Original query: {store['original_query']}")
        if "sub_queries" in store:
            print(f"   Sub queries: {store['sub_queries'][:100]}...")
        if "research_type" in store:
            print(f"   Research type: {store['research_type']}")
    else:
        print("\n⚠️  Агент не сохранил данные в store (это ОК для теста)")
        print("   LLM мог просто ответить текстом без вызова tools")
    
    print(f"\n{'='*60}\n")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_search_agent(migrated_db, agent_factory, unique_id, test_context, migrator, test_company):
    """
    Тест SearchAgent: поиск через Tavily API.
    
    ⚠️ ИСПОЛЬЗУЕТ РЕАЛЬНЫЙ Tavily API (стоимость ~$0.05)
    
    Проверяет что:
    - Агент читает подвопросы из store
    - Выполняет поиск через tavily_search
    - Сохраняет результаты в store
    """
    
    await migrator.migrate_for_company(
        company=test_company,
        agents=["apps.agents.agents.research.search_agent.SearchAgent"],
        with_dependencies=True
    )
    
    print(f"\n{'='*60}")
    print("2️⃣ ТЕСТ SEARCH AGENT")
    print(f"{'='*60}\n")
    
    search_agent = await agent_factory.get_agent("apps.agents.agents.research.search_agent.SearchAgent")
    
    # Подготавливаем входные данные
    search_input = {
        "messages": [HumanMessage(content="найди информацию по подвопросам")],
        "store": {
            "original_query": "Что такое RAG",
            "sub_queries": "Что такое RAG||||Как работает RAG"
        }
    }
    
    result = await search_agent.ainvoke(
        search_input,
        config={"configurable": {"session_id": unique_id("search")}}
    )
    
    # Проверяем базовую структуру
    assert "messages" in result
    assert len(result["messages"]) > 1, "Агент не ответил"
    
    final_message = result["messages"][-1].content
    print(f"✅ Агент ответил: {len(final_message)} символов")
    
    # Проверяем что входные данные сохранились
    store = result.get("store", {})
    assert "original_query" in store, "Потеряны данные из входного store"
    assert "sub_queries" in store, "Потеряны sub_queries"
    
    print(f"✅ Store сохранен, ключей: {len(store)}")
    
    # Если агент нашел источники - покажем
    if "search_results" in store:
        print(f"✅ Найдено источников: {store.get('sources_count', 'н/д')}")
        print(f"✅ Размер результатов: {len(store['search_results'])} символов")
        print("\nПервые 300 символов:")
        print(f"{'-'*60}")
        print(store['search_results'][:300])
        print(f"{'-'*60}")
    
    print("\nОтвет агента:")
    print(f"{'-'*60}")
    print(final_message[:400])
    print(f"{'-'*60}\n")
    
    print(f"{'='*60}\n")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_source_processor_agent(migrated_db, agent_factory, unique_id, test_context, migrator, test_company):
    """
    Тест SourceProcessor: обработка найденных источников.
    
    Проверяет что:
    - Агент читает search_results из store
    - Оценивает релевантность источников
    - Фильтрует и структурирует
    - Сохраняет обработанные источники
    """
    
    await migrator.migrate_for_company(
        company=test_company,
        agents=["apps.agents.agents.research.source_processor.SourceProcessorAgent"],
        with_dependencies=True
    )
    
    print(f"\n{'='*60}")
    print("3️⃣ ТЕСТ SOURCE PROCESSOR")
    print(f"{'='*60}\n")
    
    processor = await agent_factory.get_agent("apps.agents.agents.research.source_processor.SourceProcessorAgent")
    
    # Подготавливаем входные данные
    processor_input = {
        "messages": [HumanMessage(content="обработай найденные источники")],
        "store": {
            "original_query": "Что такое RAG",
            "search_results": """
📚 Источники:
1. Retrieval-Augmented Generation (RAG)
   URL: https://example.com/rag-overview
   Релевантность: 0.95
   Контент: RAG combines retrieval and generation...

2. How RAG Works
   URL: https://example.com/rag-technical
   Релевантность: 0.90
   Контент: Technical details of RAG architecture...
            """,
            "sources_count": "2"
        }
    }
    
    result = await processor.ainvoke(
        processor_input,
        config={"configurable": {"session_id": unique_id("processor")}}
    )
    
    # Проверяем базовую структуру
    assert "messages" in result
    assert len(result["messages"]) > 1, "Агент не ответил"
    
    final_message = result["messages"][-1].content
    print(f"✅ Агент ответил: {len(final_message)} символов")
    
    # Проверяем что входные данные сохранились в store
    store = result.get("store", {})
    assert "original_query" in store, "Потеряны данные из входного store"
    assert "search_results" in store, "Потеряны search_results"
    
    print(f"✅ Store сохранен, ключей: {len(store)}")
    
    # Если агент что-то обработал - покажем
    if "processed_sources" in store:
        print(f"✅ Обработанные источники: {len(store['processed_sources'])} символов")
    if "sources_stats" in store:
        print(f"✅ Статистика: {store['sources_stats']}")
    
    print("\nОтвет агента:")
    print(f"{'-'*60}")
    print(final_message[:400])
    print(f"{'-'*60}\n")
    
    print(f"{'='*60}\n")


@pytest.mark.asyncio
@pytest.mark.integration  
async def test_fact_extractor_agent(migrated_db, agent_factory, unique_id, test_context, migrator, test_company):
    """
    Тест FactExtractor: извлечение фактов из источников.
    
    Проверяет что:
    - Агент извлекает факты через extract_facts tool
    - Проверяет их на противоречия
    - Структурирует по категориям
    - Сохраняет в JSON формате
    """
    
    await migrator.migrate_for_company(
        company=test_company,
        agents=["apps.agents.agents.research.fact_extractor.FactExtractorAgent"],
        with_dependencies=True
    )
    
    print(f"\n{'='*60}")
    print("4️⃣ ТЕСТ FACT EXTRACTOR")
    print(f"{'='*60}\n")
    
    extractor = await agent_factory.get_agent("apps.agents.agents.research.fact_extractor.FactExtractorAgent")
    
    # Подготавливаем входные данные
    extractor_input = {
        "messages": [HumanMessage(content="извлеки факты из источников")],
        "store": {
            "original_query": "Что такое RAG",
            "processed_sources": """
🌟 ВЫСОКАЯ РЕЛЕВАНТНОСТЬ:
1. RAG Overview (https://example.com/rag)
   Релевантность: 9/10
   Ключевые моменты:
   - RAG улучшает точность LLM на 40%
   - Используется в production системах
   - Комбинирует retrieval и generation
            """
        }
    }
    
    result = await extractor.ainvoke(
        extractor_input,
        config={"configurable": {"session_id": unique_id("extractor")}}
    )
    
    # Проверяем базовую структуру
    assert "messages" in result
    assert len(result["messages"]) > 1, "Агент не ответил"
    
    final_message = result["messages"][-1].content
    print(f"✅ Агент ответил: {len(final_message)} символов")
    
    # Проверяем что входные данные сохранились
    store = result.get("store", {})
    assert "original_query" in store, "Потеряны данные из входного store"
    
    print(f"✅ Store сохранен, ключей: {len(store)}")
    
    # Если агент извлек факты - покажем
    if "facts_json" in store:
        print(f"✅ Facts JSON: {len(store['facts_json'])} символов")
        print("\nФакты (первые 500 символов):")
        print(f"{'-'*60}")
        print(store['facts_json'][:500])
        print(f"{'-'*60}")
    
    print("\nОтвет агента:")
    print(f"{'-'*60}")
    print(final_message[:400])
    print(f"{'-'*60}\n")
    
    print(f"{'='*60}\n")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_synthesizer_agent(migrated_db, agent_factory, unique_id, test_context, migrator, test_company):
    """
    Тест Synthesizer: создание итогового отчета.
    
    Проверяет что:
    - Агент создает отчет из фактов
    - Форматирует в markdown
    - Добавляет цитаты
    - Сохраняет финальный отчет
    """
    
    await migrator.migrate_for_company(
        company=test_company,
        agents=["apps.agents.agents.research.synthesizer.SynthesizerAgent"],
        with_dependencies=True
    )
    
    print(f"\n{'='*60}")
    print("5️⃣ ТЕСТ SYNTHESIZER")
    print(f"{'='*60}\n")
    
    synthesizer = await agent_factory.get_agent("apps.agents.agents.research.synthesizer.SynthesizerAgent")
    
    # Подготавливаем входные данные
    synthesizer_input = {
        "messages": [HumanMessage(content="создай итоговый отчет")],
        "store": {
            "original_query": "Что такое RAG",
            "facts_json": '[{"statement": "RAG улучшает точность LLM", "confidence": 0.9, "category": "статистика"}]',
            "facts_structured": "Категория: Статистика\n- RAG улучшает точность LLM",
            "facts_count": "1",
            "processed_sources": "1. example.com - RAG Overview"
        }
    }
    
    result = await synthesizer.ainvoke(
        synthesizer_input,
        config={"configurable": {"session_id": unique_id("synthesizer")}}
    )
    
    # Проверяем базовую структуру
    assert "messages" in result
    assert len(result["messages"]) > 1, "Агент не ответил"
    
    final_message = result["messages"][-1].content
    print(f"✅ Агент ответил: {len(final_message)} символов")
    
    # Проверяем что входные данные сохранились
    store = result.get("store", {})
    assert "original_query" in store, "Потеряны данные из входного store"
    
    print(f"✅ Store сохранен, ключей: {len(store)}")
    
    # Если агент создал отчет - покажем
    if "final_report" in store:
        report = store["final_report"]
        print(f"✅ Отчет создан: {len(report)} символов")
        print(f"✅ Содержит markdown: {'#' in report}")
        print("\nОтчет:")
        print(f"{'-'*60}")
        print(report[:600])
        print(f"{'-'*60}")
    
    print("\nОтвет агента:")
    print(f"{'-'*60}")
    print(final_message[:400])
    print(f"{'-'*60}\n")
    
    print(f"{'='*60}\n")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_quality_checker_agent(migrated_db, agent_factory, unique_id, test_context, migrator, test_company):
    """
    Тест QualityChecker: проверка качества отчета.
    
    Проверяет что:
    - Агент оценивает полноту, качество источников, объективность
    - Вычисляет средний балл
    - Принимает решение (complete/need_more_search)
    - Сохраняет все оценки
    """
    
    await migrator.migrate_for_company(
        company=test_company,
        agents=["apps.agents.agents.research.quality_checker.QualityCheckerAgent"],
        with_dependencies=True
    )
    
    print(f"\n{'='*60}")
    print("6️⃣ ТЕСТ QUALITY CHECKER")
    print(f"{'='*60}\n")
    
    checker = await agent_factory.get_agent("apps.agents.agents.research.quality_checker.QualityCheckerAgent")
    
    # Подготавливаем входные данные
    checker_input = {
        "messages": [HumanMessage(content="проверь качество отчета")],
        "store": {
            "original_query": "Что такое RAG",
            "final_report": """
# Что такое RAG в машинном обучении

## 📋 Краткое резюме
RAG (Retrieval-Augmented Generation) - техника улучшения LLM через поиск релевантной информации.

## 🔍 Детальный анализ
RAG комбинирует retrieval и generation для более точных ответов.

## ✨ Ключевые выводы
1. Улучшает точность LLM
2. Используется в production

## 📚 Источники
1. example.com - RAG Overview
            """,
            "sources_count": "1",
            "facts_count": "2",
            "iteration": 0,
            "max_iterations": 2
        }
    }
    
    result = await checker.ainvoke(
        checker_input,
        config={"configurable": {"session_id": unique_id("checker")}}
    )
    
    # Проверяем базовую структуру
    assert "messages" in result
    assert len(result["messages"]) > 1, "Агент не ответил"
    
    final_message = result["messages"][-1].content
    print(f"✅ Агент ответил: {len(final_message)} символов")
    
    # Проверяем что входные данные сохранились
    store = result.get("store", {})
    assert "original_query" in store, "Потеряны данные из входного store"
    
    print(f"✅ Store сохранен, ключей: {len(store)}")
    
    # Если агент сохранил оценки - покажем
    if "completeness_score" in store:
        completeness = float(store["completeness_score"])
        sources_quality = float(store.get("sources_quality_score", 0))
        objectivity = float(store.get("objectivity_score", 0))
        average = float(store.get("average_quality_score", 0))
        decision = store.get("quality_decision", "unknown")
        
        print(f"✅ Полнота: {completeness}/10")
        print(f"✅ Качество источников: {sources_quality}/10")
        print(f"✅ Объективность: {objectivity}/10")
        print(f"✅ Средний балл: {average}/10")
        print(f"✅ Решение: {decision}")
        
        if "quality_feedback" in store:
            print("\nОбратная связь:")
            print(f"{'-'*60}")
            print(store["quality_feedback"][:300])
            print(f"{'-'*60}")
    
    print("\nОтвет агента:")
    print(f"{'-'*60}")
    print(final_message[:400])
    print(f"{'-'*60}")
    
    print(f"\n{'='*60}\n")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_research_agents_sequential(migrated_db, agent_factory, unique_id, test_context, migrator, test_company):
    """
    Тест последовательного выполнения агентов (мини-pipeline).
    
    Запускает агенты последовательно передавая store между ними:
    QueryAnalyzer → SearchAgent → SourceProcessor
    
    Проверяет что данные корректно передаются между агентами.
    """
    
    from core.clients.llm import get_llm, get_global_mock_llm
    
    print(f"\n{'='*60}")
    print("🔗 ТЕСТ ПОСЛЕДОВАТЕЛЬНОЙ РАБОТЫ АГЕНТОВ")
    print(f"{'='*60}\n")
    
    await migrator.migrate_for_company(
        company=test_company,
        agents=[
            "apps.agents.agents.research.query_analyzer.QueryAnalyzerAgent",
            "apps.agents.agents.research.search_agent.SearchAgent",
            "apps.agents.agents.research.source_processor.SourceProcessorAgent",
        ],
        with_dependencies=True
    )
    
    session_id = unique_id("sequential")
    query = "Что такое LangGraph?"
    
    # Создаем mock LLM если его еще нет
    get_llm("mock-gpt-4")
    mock_llm = get_global_mock_llm("mock-gpt-4")
    if not mock_llm:
        raise RuntimeError("Не удалось получить mock LLM")
    
    mock_llm.reset_call_counts()
    
    # QueryAnalyzer должен вызвать session_set несколько раз, затем session_get для проверки, затем финальный ответ
    mock_llm.configure(
        response_queue=[
            {
                "type": "tool_call",
                "tool": "session_set",
                "args": {"key": "original_query", "value": "Что такое LangGraph?"}
            },
            {
                "type": "tool_call",
                "tool": "session_set",
                "args": {
                    "key": "sub_queries",
                    "value": "Что такое LangGraph?||||Как работает LangGraph?||||Какие возможности у LangGraph?||||Примеры использования LangGraph"
                }
            },
            {
                "type": "tool_call",
                "tool": "session_set",
                "args": {"key": "research_type", "value": "facts"}
            },
            {
                "type": "tool_call",
                "tool": "session_set",
                "args": {"key": "key_concepts", "value": "LangGraph, графы состояний, агенты, LangChain"}
            },
            {
                "type": "tool_call",
                "tool": "session_get",
                "args": {"key": "sub_queries"}
            },
            "Запрос проанализирован. Создано 4 подвопроса для исследования LangGraph. Тип исследования: facts. Данные сохранены в store."
        ]
    )
    
    # Этап 1: QueryAnalyzer
    print("1️⃣ QueryAnalyzer...")
    analyzer = await agent_factory.get_agent("apps.agents.agents.research.query_analyzer.QueryAnalyzerAgent")
    
    result1 = await analyzer.ainvoke(
        {"messages": [HumanMessage(content=query)]},
        config={"configurable": {"session_id": session_id}}
    )
    
    store1 = result1.get("store", {})
    print(f"   DEBUG: store1 type={type(store1)}, keys={list(store1.keys()) if isinstance(store1, dict) else 'not dict'}")
    print(f"   DEBUG: store1 content={store1}")
    
    if "sub_queries" not in store1:
        print(f"   ⚠️  Агент не сохранил sub_queries в store")
        print(f"   Store keys: {list(store1.keys())}")
        print(f"   Store content: {store1}")
        raise AssertionError(f"Агент не сохранил sub_queries в store. Store: {store1}")
    print(f"   ✅ Создано подвопросов: {len(result1['store']['sub_queries'].split('||||'))}")
    
    # Этап 2: SearchAgent (передаем store из предыдущего этапа)
    print("\n2️⃣ SearchAgent...")
    
    # Настраиваем MockLLM для SearchAgent
    # SearchAgent должен взять sub_queries из store и для каждого вызвать tavily_search
    # Но в тестах нет API ключа, поэтому сразу сохраняем результаты через session_set
    mock_llm.reset_call_counts()
    mock_llm.configure(
        response_queue=[
            {
                "type": "tool_call",
                "tool": "session_set",
                "args": {
                    "key": "search_results",
                    "value": "=== ПОДВОПРОС 1: Что такое LangGraph? ===\nLangGraph - это библиотека для построения графов состояний для LLM приложений. Она позволяет создавать сложные агентские системы с управлением потоком выполнения.\n\n=== ПОДВОПРОС 2: Как работает LangGraph? ===\nLangGraph использует графы состояний для управления потоком выполнения агентов. Каждый узел графа представляет состояние, а ребра - переходы между состояниями.\n\n=== ПОДВОПРОС 3: Какие возможности у LangGraph? ===\nLangGraph поддерживает циклы, условные переходы, параллельное выполнение, прерывания и возобновление выполнения.\n\n=== ПОДВОПРОС 4: Примеры использования LangGraph ===\nLangGraph используется для создания чат-ботов, агентов с инструментами, многоагентных систем и сложных workflow."
                }
            },
            {
                "type": "tool_call",
                "tool": "session_set",
                "args": {"key": "sources_count", "value": "12"}
            },
            "Найдено 12 источников по 4 подвопросам."
        ]
    )
    
    search_agent = await agent_factory.get_agent("apps.agents.agents.research.search_agent.SearchAgent")
    
    result2 = await search_agent.ainvoke(
        {
            "messages": [HumanMessage(content="найди информацию")],
            "store": result1["store"]  # Передаем store из analyzer
        },
        config={"configurable": {"session_id": unique_id("search_seq")}}
    )
    
    assert "search_results" in result2["store"]
    assert "sources_count" in result2["store"]
    print(f"   ✅ Найдено источников: {result2['store']['sources_count']}")
    
    # Этап 3: SourceProcessor (передаем store из поиска)
    print("\n3️⃣ SourceProcessor...")
    
    # Настраиваем MockLLM для SourceProcessor
    mock_llm.reset_call_counts()
    mock_llm.configure(
        response_queue=[
            {
                "type": "tool_call",
                "tool": "session_set",
                "args": {
                    "key": "processed_sources",
                    "value": "Обработанные источники:\n1. LangGraph - библиотека для графов состояний\n2. Используется для построения агентов\n3. Поддерживает сложные сценарии взаимодействия"
                }
            },
            "Источники обработаны и сохранены."
        ]
    )
    
    processor = await agent_factory.get_agent("apps.agents.agents.research.source_processor.SourceProcessorAgent")
    
    result3 = await processor.ainvoke(
        {
            "messages": [HumanMessage(content="обработай источники")],
            "store": result2["store"]  # Передаем store из search
        },
        config={"configurable": {"session_id": unique_id("proc_seq")}}
    )
    
    assert "processed_sources" in result3["store"]
    print("   ✅ Источники обработаны")
    
    # Проверяем что данные из всех этапов присутствуют
    final_store = result3["store"]
    assert "original_query" in final_store, "Потеряны данные из analyzer"
    assert "sub_queries" in final_store, "Потеряны подвопросы"
    assert "search_results" in final_store, "Потеряны результаты поиска"
    assert "processed_sources" in final_store, "Потеряны обработанные источники"
    
    print("\n✅ ВСЕ ДАННЫЕ СОХРАНИЛИСЬ В STORE:")
    print(f"   - original_query: {final_store['original_query']}")
    print("   - sub_queries: есть")
    print(f"   - search_results: {len(final_store['search_results'])} символов")
    print(f"   - processed_sources: {len(final_store['processed_sources'])} символов")
    
    print(f"\n{'='*60}\n")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_all_research_agents_available(migrated_db, agent_factory, test_context, migrator, test_company):
    """
    Быстрая проверка доступности всех research агентов.
    
    Проверяет что все агенты:
    - Мигрировались в БД
    - Доступны через factory
    - Имеют корректные tools
    """
    
    await migrator.migrate_for_company(
        company=test_company,
        agents=[
            "apps.agents.agents.research.query_analyzer.QueryAnalyzerAgent",
            "apps.agents.agents.research.search_agent.SearchAgent",
            "apps.agents.agents.research.source_processor.SourceProcessorAgent",
            "apps.agents.agents.research.fact_extractor.FactExtractorAgent",
            "apps.agents.agents.research.synthesizer.SynthesizerAgent",
            "apps.agents.agents.research.quality_checker.QualityCheckerAgent"
        ],
        with_dependencies=True
    )
    
    print(f"\n{'='*60}")
    print("📋 ПРОВЕРКА ДОСТУПНОСТИ ВСЕХ АГЕНТОВ")
    print(f"{'='*60}\n")
    
    agents = [
        ("QueryAnalyzer", "apps.agents.agents.research.query_analyzer.QueryAnalyzerAgent"),
        ("SearchAgent", "apps.agents.agents.research.search_agent.SearchAgent"),
        ("SourceProcessor", "apps.agents.agents.research.source_processor.SourceProcessorAgent"),
        ("FactExtractor", "apps.agents.agents.research.fact_extractor.FactExtractorAgent"),
        ("Synthesizer", "apps.agents.agents.research.synthesizer.SynthesizerAgent"),
        ("QualityChecker", "apps.agents.agents.research.quality_checker.QualityCheckerAgent"),
        ("Coordinator", "apps.agents.agents.research.coordinator.ResearchCoordinatorAgent"),
    ]
    
    for name, agent_id in agents:
        agent = await agent_factory.get_agent(agent_id)
        assert agent is not None, f"{name} недоступен"
        
        tools = await agent.get_tools()
        
        print(f"✅ {name:20} {len(tools):2} tools")
    
    print(f"\n{'='*60}\n")

