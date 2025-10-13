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


# Тарифные цены: множители к базовой цене
TARIFF_PRICES = {
    TariffPlan.FREE: {
        "llm": {"*": 1.5},
        "tools": {"*": 1.5},
    },
    TariffPlan.BASIC: {
        "llm": {"*": 1.25},
        "tools": {"*": 1.25},
    },
    TariffPlan.PREMIUM: {
        "llm": {"*": 1.1},
        "tools": {"*": 1.1},
    },
    TariffPlan.ENTERPRISE: {
        "llm": {"*": 1.1},
        "tools": {"*": 1.1},
    }
}

# Для обратной совместимости (пока не используется)
TARIFF_LIMITS = {}
