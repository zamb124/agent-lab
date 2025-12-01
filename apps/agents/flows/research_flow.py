"""
Research Flow - точка входа для системы исследований.

Полный цикл глубокого исследования: анализ → поиск → обработка → факты → синтез → проверка.

НАСТРОЙКА СКОРОСТИ И ГЛУБИНЫ:

1. Быстрое исследование (1-2 минуты):
   - max_iterations: 1
   - max_sub_queries: 2-3
   - max_sources_per_query: 2-3
   - search_depth: "basic"
   
2. Среднее исследование (3-5 минут):
   - max_iterations: 2
   - max_sub_queries: 3-4
   - max_sources_per_query: 4-5
   - search_depth: "basic"
   
3. Глубокое исследование (5-10 минут):
   - max_iterations: 2-3
   - max_sub_queries: 4-5
   - max_sources_per_query: 5-7
   - search_depth: "advanced"
"""

import logging
from apps.agents.models.core_models import FlowConfig, FlowAuthor

logger = logging.getLogger(__name__)


# Конфигурация Research Flow
research_flow_config = FlowConfig(
    name="Research Flow",
    description="""# Research Flow - Глубокое исследование

Полный цикл исследования: анализ запроса → поиск → обработка → извлечение фактов → синтез отчета → проверка качества.

## Как использовать

Просто отправьте запрос исследования:
- "Исследуй тему RAG в LLM"
- "Сравни LangChain и LlamaIndex"
- "Что такое Schema-Guided Reasoning?"

## Настройки производительности

### 🚀 Быстрое исследование (1-2 минуты)
```
max_iterations: 1
max_sub_queries: 2-3
max_sources_per_query: 2-3
search_depth: "basic"
```

### ⚡ Среднее исследование (3-5 минут)
```
max_iterations: 2
max_sub_queries: 3-4
max_sources_per_query: 4-5
search_depth: "basic"
```

### 🎯 Глубокое исследование (5-10 минут)
```
max_iterations: 2-3
max_sub_queries: 4-5
max_sources_per_query: 5-7
search_depth: "advanced"
```

## Параметры

### Store (изменяемые во время выполнения)

- **max_iterations** (число): Количество итераций проверки качества
  - `1` = быстро, одна проверка
  - `2-3` = тщательно, несколько проверок
  - По умолчанию: `1`

- **max_sub_queries** (число): Максимальное количество подвопросов
  - `2-3` = быстрое исследование
  - `4-5` = детальное исследование
  - По умолчанию: `3`

### Variables (статические настройки)

- **max_sources_per_query** (число): Источников на каждый подвопрос
  - `2-3` = быстро, базовая информация
  - `5-7` = глубоко, много деталей
  - По умолчанию: `3`

- **search_depth** (строка): Режим глубины поиска
  - `"basic"` = быстрый поиск, краткие выдержки
  - `"advanced"` = глубокий поиск, полный контент страниц
  - По умолчанию: `"basic"`

- **quality_threshold** (число): Минимальный порог качества (0-10)
  - Если средняя оценка ниже порога, запускается дополнительная итерация
  - `6.0` = строгий контроль (больше итераций)
  - `8.0` = мягкий контроль (меньше итераций)
  - По умолчанию: `7.0`

- **search_provider** (строка): Поисковый провайдер
  - `"tavily"` = оптимизирован для LLM (рекомендуется)
  - `"serper"` = Google поиск
  - По умолчанию: `"tavily"`

## Этапы исследования

1. **QueryAnalyzer** - Анализ запроса и создание подвопросов
2. **SearchAgent** - Поиск информации по подвопросам
3. **SourceProcessor** - Фильтрация и ранжирование источников
4. **FactExtractor** - Извлечение структурированных фактов
5. **Synthesizer** - Синтез финального отчета
6. **QualityChecker** - Проверка качества и решение о завершении

## Советы по оптимизации

- Для **быстрых ответов**: уменьшите `max_sub_queries` и `max_sources_per_query`
- Для **детального анализа**: увеличьте параметры и используйте `search_depth: "advanced"`
- Для **экономии токенов**: используйте `search_depth: "basic"` и меньше источников
- Для **высокого качества**: увеличьте `max_iterations` и поднимите `quality_threshold`
""",
    entry_point_agent="apps.agents.agents.research.coordinator.ResearchCoordinatorAgent",
    
    platforms={
        "api": {},
        "telegram": {
            "username": "@var:research_bot_telegram_username",
            "token": "@var:research_bot_telegram_token"
        }
    },
    
    # Статические переменные (доступны в промптах через {variable})
    variables={
        "bot_name": "Research Assistant",
        "greeting": "Я помогу провести глубокое исследование любой темы",
        "support_email": "@var:company_support_email",
        
        # Настройки поиска (влияют на скорость и глубину)
        "search_provider": "tavily",
        "max_sources_per_query": 3,  # Источников на подвопрос (2-3 = быстро, 5-7 = глубоко)
        "search_depth": "basic",     # "basic" = быстро, "advanced" = подробно с полным контентом
        
        # Настройки качества
        "min_relevance_score": 6,
        "quality_threshold": 7.0,    # Минимальный порог для завершения (ниже = больше итераций)
        
        # Стиль отчета
        "report_style": "academic",
    },
    
    # Начальные данные store (изменяются во время выполнения)
    store={
        "max_iterations": 1,         # Количество итераций проверки качества (1 = быстро, 2-3 = тщательно)
        "max_sub_queries": 3,        # Количество подвопросов (2-3 = быстро, 4-5 = детально)
        "iteration": 0,
        "show_welcome": True,
    },
    
    is_public=True,
    
    author=FlowAuthor(
        name="Humanitec Team",
        email="team@agents-lab.ru",
        website="https://agents-lab.ru",
    ),
)


# Экспорт для миграции
__all__ = ["research_flow_config"]

