"""
LLMResourceProvider - провайдер для llm ресурсов.
"""

from typing import Any, Dict

from apps.flows.src.models import ResourceDefinition, LLMResourceConfig
from apps.flows.src.resources.providers.base import BaseResourceProvider
from apps.flows.src.resources.wrappers import LLMResource
from core.logging import get_logger

logger = get_logger(__name__)


class LLMResourceProvider(BaseResourceProvider):
    """
    Провайдер для LLM ресурсов.
    
    Создаёт LLMResource для генерации текста.
    """
    
    def __init__(self, container: Any = None):
        self._container = container
    
    async def resolve(
        self,
        definition: ResourceDefinition,
        variables: Dict[str, Any],
    ) -> LLMResource:
        """
        Создаёт LLMResource.
        
        Args:
            definition: Определение ресурса с llm конфигом
            variables: Переменные агента
            
        Returns:
            LLMResource для работы с LLM
        """
        resolved_config = self._resolve_variable_refs(definition.config, variables)
        config = LLMResourceConfig.model_validate(resolved_config)
        
        logger.debug(
            f"LLM resource '{definition.resource_id}' loaded: "
            f"provider={config.provider}, model={config.model}"
        )
        
        return LLMResource(
            provider=config.provider,
            model=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            api_key=config.api_key,
            base_url=config.base_url,
        )
