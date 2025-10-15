"""
Research Flow - точка входа для системы исследований.

Полный цикл глубокого исследования: анализ → поиск → обработка → факты → синтез → проверка.
"""

import logging
from app.models.core_models import FlowConfig, FlowAuthor

logger = logging.getLogger(__name__)


# Конфигурация Research Flow
research_flow_config = FlowConfig(
    name="Research Flow",
    description="Глубокое исследование с поиском в интернете и синтезом отчета",
    entry_point_agent="app.agents.research.coordinator.ResearchCoordinatorAgent",
    
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
        
        # Настройки поиска
        "search_provider": "tavily",
        "max_sources_per_query": 3,
        "search_depth": "basic",
        
        # Настройки качества
        "min_relevance_score": 6,
        "quality_threshold": 7.0,
        
        # Стиль отчета
        "report_style": "academic",
    },
    
    # Начальные данные store (изменяются во время выполнения)
    store={
        "max_iterations": 1,
        "max_sub_queries": 3,
        "iteration": 0,
        "show_welcome": True,
    },
    
    is_public=True,
    
    author=FlowAuthor(
        name="Agent Lab Team",
        email="team@agents-lab.ru",
        website="https://agents-lab.ru",
    ),
)


# Экспорт для миграции
__all__ = ["research_flow_config"]

