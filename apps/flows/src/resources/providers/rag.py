"""
RAGResourceProvider - провайдер для rag ресурсов.
"""

from typing import Any, Dict

from apps.flows.src.models import ResourceDefinition, RAGResourceConfig
from apps.flows.src.resources.providers.base import BaseResourceProvider
from apps.flows.src.resources.wrappers import RAGResource
from core.logging import get_logger

logger = get_logger(__name__)


class RAGResourceProvider(BaseResourceProvider):
    """
    Провайдер для RAG ресурсов.
    
    Создаёт RAGResource для доступа к семантическому поиску.
    """
    
    def __init__(self, container: Any = None):
        self._container = container
    
    async def resolve(
        self,
        definition: ResourceDefinition,
        variables: Dict[str, Any],
    ) -> RAGResource:
        """
        Создаёт RAGResource.
        
        Args:
            definition: Определение ресурса с rag конфигом
            variables: Переменные агента
            
        Returns:
            RAGResource для работы с RAG namespace
        """
        resolved_config = self._resolve_variable_refs(definition.config, variables)
        config = RAGResourceConfig.model_validate(resolved_config)
        
        logger.debug(
            f"RAG resource '{definition.resource_id}' loaded: "
            f"namespace={config.namespace}, provider={config.provider}"
        )
        
        return RAGResource(
            config.namespace,
            self._container,
            provider=config.provider,
            default_top_k=config.default_top_k,
            company_id=config.company_id,
            search_options=config.search_options,
            index_profile_config=config.index_profile_config,
        )
