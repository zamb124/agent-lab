"""
Модели для системы биллинга и тарификации.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any
from pydantic import BaseModel, ConfigDict
from enum import Enum

from core.fields import Field


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
    EMBEDDING_REQUEST = "embedding_request"  # Запрос к Embedding API
    AGENT_EXECUTION = "agent_execution"  # Выполнение агента
    FLOW_EXECUTION = "flow_execution"    # Выполнение флоу
    FILE_UPLOAD = "file_upload"     # Загрузка файла
    STORAGE_USAGE = "storage_usage" # Использование хранилища


class UsageRecord(BaseModel):
    """Запись об использовании ресурсов"""
    
    model_config = ConfigDict(storage_prefix="usage")
    
    usage_id: str = Field(
        title="ID записи",
        json_schema_extra={"readOnly": True}
    )
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
# Может быть переопределено в конфигурации сервиса
DEFAULT_TARIFF_PRICES = {
    TariffPlan.FREE: {
        "llm": {"*": 1.5},
        "embedding": {"*": 1.5},
        "livekit": {"*": 1.5},
        "billing": {"*": 1.0},
    },
    TariffPlan.BASIC: {
        "llm": {"*": 1.25},
        "embedding": {"*": 1.25},
        "livekit": {"*": 1.25},
        "billing": {"*": 1.0},
    },
    TariffPlan.PREMIUM: {
        "llm": {"*": 1.1},
        "embedding": {"*": 1.1},
        "livekit": {"*": 1.1},
        "billing": {"*": 1.0},
    },
    TariffPlan.ENTERPRISE: {
        "llm": {"*": 1.1},
        "embedding": {"*": 1.1},
        "livekit": {"*": 1.1},
        "billing": {"*": 1.0},
    },
}

# Для обратной совместимости
TARIFF_PRICES = DEFAULT_TARIFF_PRICES
TARIFF_LIMITS = {}

