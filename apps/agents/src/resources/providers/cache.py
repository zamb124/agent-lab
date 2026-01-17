"""
CacheResourceProvider - провайдер для cache ресурсов.
"""

from typing import Any, Dict

from apps.agents.src.models import ResourceDefinition, CacheResourceConfig
from apps.agents.src.resources.providers.base import BaseResourceProvider
from apps.agents.src.resources.wrappers import CacheResource
from core.logging import get_logger

logger = get_logger(__name__)


class CacheResourceProvider(BaseResourceProvider):
    """
    Провайдер для Cache ресурсов.
    
    Создаёт CacheResource для работы с Redis.
    """
    
    def __init__(self, container: Any = None):
        self._container = container
    
    async def resolve(
        self,
        definition: ResourceDefinition,
        variables: Dict[str, Any],
    ) -> CacheResource:
        """
        Создаёт CacheResource.
        
        Args:
            definition: Определение ресурса с cache конфигом
            variables: Переменные агента
            
        Returns:
            CacheResource для работы с кэшем
        """
        resolved_config = self._resolve_variable_refs(definition.config, variables)
        config = CacheResourceConfig.model_validate(resolved_config)
        
        logger.debug(
            f"Cache resource '{definition.resource_id}' loaded: "
            f"namespace={config.namespace}, ttl={config.ttl}"
        )
        
        return CacheResource(
            namespace=config.namespace,
            ttl=config.ttl,
            container=self._container,
        )
