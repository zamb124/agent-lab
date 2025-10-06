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


# Тарифные цены (переопределения базовых цен)
# -1 = бесплатно, None = использовать базовую цену
TARIFF_PRICES = {
    TariffPlan.FREE: {
        # OpenAI - полная цена
        "openai": {},  # Используем базовые цены
        
        # Gemini - полная цена
        "gemini": {},
        
        # Yandex - полная цена
        "yandex": {},
        
        # Anthropic - полная цена
        "anthropic": {},
        
        # Инструменты - полная цена
        "tools": {},
    },
    TariffPlan.BASIC: {
        # OpenAI - скидка 20%
        "openai": {
            "gpt-4": 0.8,  # Множитель к базовой цене
            "gpt-4o": 0.8,
            "gpt-3.5-turbo": 0.8,
        },
        
        # Gemini - скидка 20%
        "gemini": {
            "*": 0.8,  # Для всех моделей
        },
        
        # Yandex - скидка 20%
        "yandex": {
            "*": 0.8,
        },
        
        # Anthropic - скидка 20%
        "anthropic": {
            "*": 0.8,
        },
        
        # Инструменты - скидка 30%
        "tools": {
            "*": 0.7,
        },
    },
    TariffPlan.PREMIUM: {
        # OpenAI - скидка 50%
        "openai": {
            "*": 0.5,
        },
        
        # Gemini - скидка 50%
        "gemini": {
            "*": 0.5,
        },
        
        # Yandex - скидка 50%
        "yandex": {
            "*": 0.5,
        },
        
        # Anthropic - скидка 50%
        "anthropic": {
            "*": 0.5,
        },
        
        # Инструменты - скидка 70%
        "tools": {
            "*": 0.3,
        },
    },
    TariffPlan.ENTERPRISE: {
        # Все бесплатно
        "openai": {"*": 0.0},
        "gemini": {"*": 0.0},
        "yandex": {"*": 0.0},
        "anthropic": {"*": 0.0},
        "tools": {"*": 0.0},
    }
}

# Для обратной совместимости (пока не используется)
TARIFF_LIMITS = {}
