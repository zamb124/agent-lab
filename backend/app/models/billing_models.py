"""
Модели для системы биллинга и тарификации.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class TariffPlan(str, Enum):
    """Тарифные планы"""
    FREE = "free"           # Бесплатный
    BASIC = "basic"         # Базовый  
    PREMIUM = "premium"     # Премиум
    ENTERPRISE = "enterprise" # Корпоративный


class UsageType(str, Enum):
    """Типы использования ресурсов"""
    TOOL_CALL = "tool_call"         # Вызов инструмента
    LLM_REQUEST = "llm_request"     # Запрос к LLM
    AGENT_EXECUTION = "agent_execution"  # Выполнение агента
    FLOW_EXECUTION = "flow_execution"    # Выполнение флоу
    FILE_UPLOAD = "file_upload"     # Загрузка файла
    STORAGE_USAGE = "storage_usage" # Использование хранилища


class UsageRecord(BaseModel):
    """Запись об использовании ресурсов"""
    
    class Config:
        storage_prefix = "usage"
    
    usage_id: str = Field(title="ID записи", readonly=True)
    user_id: str = Field(title="ID пользователя")
    company_id: str = Field(title="ID компании")
    session_id: Optional[str] = Field(default=None, title="ID сессии")
    
    # Что использовалось
    usage_type: UsageType = Field(title="Тип использования")
    resource_name: str = Field(title="Название ресурса")  # "weather_api", "gpt-4", etc
    
    # Стоимость и метрики
    cost: float = Field(default=0.0, title="Стоимость в RUB")
    quantity: int = Field(default=1, title="Количество")  # токены, вызовы, байты
    
    # Метаданные
    metadata: Dict[str, Any] = Field(default_factory=dict, title="Дополнительные данные")
    
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Глобальные тарифные лимиты по провайдерам
TARIFF_LIMITS = {
    TariffPlan.FREE: {
        # OpenAI
        "openai": {
            "gpt-4": 0,              # Недоступно
            "gpt-4o": 0,             # Недоступно  
            "gpt-3.5-turbo": 100,    # 100 запросов в месяц
        },
        # Gemini
        "gemini": {
            "gemini-2.0-flash-exp": 20,      # 20 запросов
            "gemini-2.5-pro": 0,             # Недоступно
            "gemini-1.5-flash": 50,          # 50 запросов
            "gemini-1.5-pro": 0,             # Недоступно
        },
        # Yandex
        "yandex": {
            "yandexgpt/latest": 50,          # 50 запросов
        },
        # Anthropic
        "anthropic": {
            "claude-3-sonnet": 0,            # Недоступно
        },
        
        # Инструменты
        "tools": {
            "weather_api": 50,
            "travel_suggest": 20,
            "calculator": -1,
            "nano_banana_generation": 5,
            "fashn_buyer_agent": -1,
        },
        
        # Ресурсы платформы
        "platform": {
            "max_agents": 3,
            "max_flows": 2,
        }
    },
    TariffPlan.BASIC: {
        "openai": {
            "gpt-4": 10,
            "gpt-4o": 5,
            "gpt-3.5-turbo": 1000,
        },
        "gemini": {
            "gemini-2.0-flash-exp": 200,
            "gemini-2.5-pro": 50,
            "gemini-1.5-flash": 500,
            "gemini-1.5-pro": 100,
        },
        "yandex": {
            "yandexgpt/latest": 500,
        },
        "anthropic": {
            "claude-3-sonnet": 50,
        },
        "tools": {
            "weather_api": 500,
            "travel_suggest": 200,
            "calculator": -1,
            "nano_banana_generation": 50,
            "fashn_buyer_agent": -1,
        },
        "platform": {
            "max_agents": 10,
            "max_flows": 5,
        }
    },
    TariffPlan.PREMIUM: {
        "openai": {
            "gpt-4": 100,
            "gpt-4o": -1,            # Без лимитов для premium
            "gpt-4o-mini": -1,       # Без лимитов для premium
            "gpt-3.5-turbo": -1,
        },
        "gemini": {
            "gemini-2.0-flash-exp": -1,
            "gemini-2.5-pro": -1,
            "gemini-1.5-flash": -1,
            "gemini-1.5-pro": -1,
        },
        "yandex": {
            "yandexgpt/latest": -1,
        },
        "anthropic": {
            "claude-3-sonnet": -1,
        },
        "tools": {
            "weather_api": -1,
            "travel_suggest": -1,
            "calculator": -1,
            "nano_banana_generation": -1,
            "fashn_buyer_agent": -1,
        },
        "platform": {
            "max_agents": 50,
            "max_flows": 20,
        }
    },
    TariffPlan.ENTERPRISE: {
        # Все без лимитов
        "openai": {"*": -1},
        "gemini": {"*": -1},
        "yandex": {"*": -1},
        "anthropic": {"*": -1},
        "tools": {"*": -1},
        "platform": {"*": -1},
    }
}
