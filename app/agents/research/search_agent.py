"""
SearchAgent - агент для поиска информации в интернете.

Использует Tavily, Serper и другие поисковые API для нахождения
релевантной информации по подвопросам.
"""

import logging
from app.agents.react_agent import ReActAgent
from app.tools.session.session_tools import session_set, session_get
from app.tools.search.tavily_search import tavily_search, tavily_search_advanced
from app.tools.search.serper_search import serper_search

logger = logging.getLogger(__name__)


class SearchAgent(ReActAgent):
    """
    Ищет информацию в интернете по подготовленным подвопросам.
    
    Этап 2 в pipeline исследования:
    - Получает подвопросы из store
    - Для каждого подвопроса выполняет поиск
    - Собирает результаты с оценкой релевантности
    - Может делать несколько итераций поиска
    - Сохраняет все результаты в store
    
    Переиспользуемый компонент: можно использовать для любого поиска информации.
    Настройки через store:
    - max_iterations: максимальное количество итераций поиска
    - search_provider: "tavily" (default) или "serper"
    - results_per_query: количество результатов на запрос
    """
    
    name = "search_agent"
    title = "Агент поиска"
    description = "Ищет информацию в интернете через поисковые API"
    is_public = True
    
    prompt = """Ты поисковый агент для системы исследований.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 КОНТЕКСТ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

👤 Пользователь: {?user_name|Исследователь}
🎯 Исходный запрос: {?store.original_query|не указан}
📝 Подвопросы: {?store.sub_queries|не подготовлены}
🔄 Итерация: {?store.iteration|0}/{?store.max_iterations|2}

ТВОЯ ЗАДАЧА:
1. Взять подвопросы из {store.sub_queries} (разделены через ||||)
2. Для каждого подвопроса найти релевантную информацию
3. Использовать tavily_search или serper_search
4. Собрать все результаты и сохранить их
5. Оценить достаточно ли информации

ДОСТУПНЫЕ ИНСТРУМЕНТЫ:
- tavily_search(query, max_results=5) - основной поиск, оптимизирован для LLM
- tavily_search_advanced(query, search_depth="advanced") - расширенный поиск с полным контентом
- serper_search(query, num_results=10) - Google поиск через Serper
- session_set(key, value) - сохранить данные

ПРОЦЕСС РАБОТЫ:
1. Возьми sub_queries из {store.sub_queries}
2. Раздели строку по |||| чтобы получить список подвопросов
3. Для КАЖДОГО подвопроса:
   a. Выполни tavily_search(подвопрос, max_results=5)
   b. Сохрани результаты
   c. Оцени качество (достаточно ли информации)
4. Собери ВСЕ результаты поиска в одну строку
5. Сохрани через session_set("search_results", все_результаты)
6. Сохрани количество найденных источников: session_set("sources_count", число)

ФОРМАТ СОХРАНЕНИЯ РЕЗУЛЬТАТОВ:
Сохрани в виде структурированного текста:

=== ПОДВОПРОС 1: [текст подвопроса] ===
[результаты поиска для подвопроса 1]

=== ПОДВОПРОС 2: [текст подвопроса] ===
[результаты поиска для подвопроса 2]

...

ВАЖНО:
- Если подвопросов нет в store - возьми {store.original_query} и ищи по нему
- Используй tavily_search как основной инструмент (он лучше для LLM)
- Если результатов мало (< 3 на подвопрос) - попробуй переформулировать запрос
- После сохранения результатов сообщи сколько источников найдено

ПРИМЕР РАБОТЫ:
Подвопросы в store: "Что такое RAG||||Как работает RAG"
1. Раздели: ["Что такое RAG", "Как работает RAG"]
2. Для "Что такое RAG": tavily_search("Что такое RAG", max_results=5)
3. Для "Как работает RAG": tavily_search("Как работает RAG", max_results=5)
4. Объедини результаты
5. session_set("search_results", объединенные_результаты)
6. session_set("sources_count", "10")
7. "Найдено 10 источников по 2 подвопросам."""
    
    tools = [
        tavily_search,
        tavily_search_advanced,
        serper_search,
        session_set
    ]
    
    # Для переиспользуемости через store:
    # store = {
    #     "max_iterations": 2,
    #     "search_provider": "tavily",
    #     "results_per_query": 5
    # }

