"""
Фабрика для создания RAG провайдеров.
"""

import logging
from typing import Optional
from .base_provider import BaseRAGProvider
from .providers.agentset_provider import AgentsetRAGProvider
from .providers.chromadb_provider import ChromaDBRAGProvider
from core.config import get_settings

logger = logging.getLogger(__name__)

RAG_PROVIDERS = {
    "agentset": AgentsetRAGProvider,
    "chromadb": ChromaDBRAGProvider,
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
    
    logger.info(f"🔍 RAG settings: enabled={settings.rag.enabled}, default_provider={settings.rag.default_provider}")
    logger.info(f"🔍 RAG providers: {list(settings.rag.providers.keys())}")
    
    if not settings.rag.enabled:
        raise ValueError("RAG не включен в конфигурации (rag.enabled = false)")
    
    provider = provider_name or settings.rag.default_provider
    
    logger.debug(f"Creating provider: {provider}")
    
    if provider not in RAG_PROVIDERS:
        available = ", ".join(RAG_PROVIDERS.keys())
        raise ValueError(
            f"Неизвестный RAG провайдер: {provider}. Доступные: {available}"
        )
    
    provider_config = settings.rag.providers.get(provider)
    
    if not provider_config:
        raise ValueError(f"Не найдена конфигурация для провайдера: {provider}")
    
    logger.debug(f"provider_config type: {type(provider_config)}, value: {provider_config}")
    
    # Конвертируем Pydantic модель в dict для передачи в провайдер
    if hasattr(provider_config, 'model_dump'):
        config_dict = provider_config.model_dump()
    elif hasattr(provider_config, 'dict'):
        config_dict = provider_config.dict()
    elif isinstance(provider_config, dict):
        config_dict = provider_config
    else:
        raise ValueError(f"Неподдерживаемый тип конфигурации провайдера: {type(provider_config)}")
    
    logger.debug(f"config_dict: {config_dict}")
    
    if not config_dict.get("enabled", False):
        raise ValueError(f"Провайдер {provider} отключен (enabled = false)")
    
    # Получаем общую конфигурацию embedding из RAGConfig
    embedding_config = None
    if hasattr(settings.rag, 'embedding') and settings.rag.embedding:
        embedding_config = settings.rag.embedding.model_dump() if hasattr(settings.rag.embedding, 'model_dump') else dict(settings.rag.embedding)
    
    provider_class = RAG_PROVIDERS[provider]
    
    # ChromaDB принимает embedding_config отдельным параметром
    if provider == "chromadb":
        instance = provider_class(config_dict, embedding_config=embedding_config)
    else:
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






