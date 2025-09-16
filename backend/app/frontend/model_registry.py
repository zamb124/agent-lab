"""
Реестр моделей по storage_prefix
"""
from typing import Dict, Type
from pydantic import BaseModel


class ModelRegistry:
    """Реестр моделей для автоматического определения типа по storage_prefix"""
    
    _models: Dict[str, Type[BaseModel]] = {}
    
    @classmethod
    def register(cls, model_class: Type[BaseModel]):
        """Зарегистрировать модель"""
        if hasattr(model_class, 'Config') and hasattr(model_class.Config, 'storage_prefix'):
            prefix = model_class.Config.storage_prefix
            cls._models[prefix] = model_class
    
    @classmethod
    def get_model_class(cls, storage_prefix: str) -> Type[BaseModel]:
        """Получить класс модели по storage_prefix"""
        if storage_prefix not in cls._models:
            raise ValueError(f"Model not found for prefix: {storage_prefix}")
        return cls._models[storage_prefix]
    
    @classmethod
    def get_all_prefixes(cls) -> list[str]:
        """Получить все зарегистрированные префиксы"""
        return list(cls._models.keys())


# Регистрируем все модели
def register_all_models():
    """Регистрирует все модели с storage_prefix"""
    from app.core.models import AgentConfig, FlowConfig, TaskConfig, LLMConfig, GraphDefinition
    from app.identity.models import User
    
    ModelRegistry.register(AgentConfig)
    ModelRegistry.register(FlowConfig)
    ModelRegistry.register(TaskConfig)
    ModelRegistry.register(LLMConfig)
    ModelRegistry.register(GraphDefinition)
    ModelRegistry.register(User)


# Автоматическая регистрация при импорте
register_all_models()
