"""
Фабрика для создания RAG провайдеров.
"""

import logging
from typing import Optional
from .base_provider import BaseRAGProvider
from .providers.agentset_provider import AgentsetRAGProvider
from ..config import get_settings

logger = logging.getLogger(__name__)

RAG_PROVIDERS = {
    "agentset": AgentsetRAGProvider,
}


def get_rag_provider(provider_name: Optional[str] = None) -> BaseRAGProvider:
    """
    Создает RAG провайдер на основе конфигурации.
    
    Args:
        provider_name: Имя провайдера. Если None, используется default_provider
        
    Returns:
        Экземпляр RAG провайдера
    """
    settings = get_settings()
    
    if not settings.rag.enabled:
        raise ValueError("RAG не включен в конфигурации (rag.enabled = false)")
    
    provider = provider_name or settings.rag.default_provider
    
    if provider not in RAG_PROVIDERS:
        available = ", ".join(RAG_PROVIDERS.keys())
        raise ValueError(
            f"Неизвестный RAG провайдер: {provider}. Доступные: {available}"
        )
    
    provider_config = settings.rag.providers.get(provider)
    
    if not provider_config:
        raise ValueError(f"Не найдена конфигурация для провайдера: {provider}")
    
    config_dict = provider_config.model_dump() if hasattr(provider_config, 'model_dump') else dict(provider_config)
    
    if not config_dict.get("enabled", False):
        raise ValueError(f"Провайдер {provider} отключен (enabled = false)")
    
    provider_class = RAG_PROVIDERS[provider]
    instance = provider_class(config_dict)
    
    logger.info(f"Создан RAG провайдер: {provider}")
    return instance


_default_rag_provider: Optional[BaseRAGProvider] = None


def get_default_rag_provider() -> BaseRAGProvider:
    """Получает дефолтный RAG провайдер (синглтон)"""
    global _default_rag_provider
    
    if _default_rag_provider is None:
        _default_rag_provider = get_rag_provider()
    
    return _default_rag_provider


async def close_default_rag_provider():
    """Закрывает дефолтный RAG провайдер"""
    global _default_rag_provider
    
    if _default_rag_provider:
        await _default_rag_provider.close()
        _default_rag_provider = None
        logger.info("RAG провайдер закрыт")

