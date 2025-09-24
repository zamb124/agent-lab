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


# Глобальные тарифные лимиты (можно вынести в конфиг)
TARIFF_LIMITS = {
    TariffPlan.FREE: {
        # LLM лимиты (по запросам)
        "openai_gpt_4": 0,              # FREE не может использовать GPT-4
        "openai_gpt_3_5_turbo": 100,    # 100 запросов в месяц
        "yandex_yandexgpt_latest": 50,  # 50 запросов к YandexGPT
        "anthropic_claude_3_sonnet": 0, # Claude недоступен на FREE
        
        # Инструменты
        "weather_api": 50,       # 50 запросов к погоде
        "travel_suggest": 20,    # 20 предложений путешествий
        "calculator": -1,        # -1 = без лимитов
        
        # Ресурсы платформы
        "max_agents": 3,         # максимум 3 агента
        "max_flows": 2,          # максимум 2 флоу
    },
    TariffPlan.BASIC: {
        # LLM лимиты
        "openai_gpt_4": 10,             # 10 запросов GPT-4 в месяц
        "openai_gpt_3_5_turbo": 1000,   # 1000 запросов GPT-3.5
        "yandex_yandexgpt_latest": 500, # 500 запросов к YandexGPT
        "anthropic_claude_3_sonnet": 50, # 50 запросов к Claude
        
        # Инструменты
        "weather_api": 500,      
        "travel_suggest": 200,
        "calculator": -1,
        
        # Ресурсы платформы
        "max_agents": 10,
        "max_flows": 5,
    },
    TariffPlan.PREMIUM: {
        # LLM лимиты
        "openai_gpt_4": 100,
        "openai_gpt_3_5_turbo": 10000,
        "yandex_yandexgpt_latest": 5000,
        "anthropic_claude_3_sonnet": 500,
        
        # Инструменты
        "weather_api": -1,       # без лимитов
        "travel_suggest": -1,
        "calculator": -1,
        
        # Ресурсы платформы
        "max_agents": 50,
        "max_flows": 20,
    },
    TariffPlan.ENTERPRISE: {
        # Все без лимитов
        "openai_gpt_4": -1,
        "openai_gpt_3_5_turbo": -1,
        "yandex_yandexgpt_latest": -1,
        "anthropic_claude_3_sonnet": -1,
        "weather_api": -1,
        "travel_suggest": -1,
        "calculator": -1,
        "max_agents": -1,
        "max_flows": -1,
    }
}
