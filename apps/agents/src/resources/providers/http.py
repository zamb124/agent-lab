"""
HTTPResourceProvider - провайдер для http ресурсов.
"""

from typing import Any, Dict

from apps.agents.src.models import ResourceDefinition, HTTPResourceConfig
from apps.agents.src.resources.providers.base import BaseResourceProvider
from apps.agents.src.resources.wrappers import HTTPResource
from core.logging import get_logger

logger = get_logger(__name__)


class HTTPResourceProvider(BaseResourceProvider):
    """
    Провайдер для HTTP ресурсов.
    
    Создаёт HTTPResource для HTTP запросов.
    """
    
    async def resolve(
        self,
        definition: ResourceDefinition,
        variables: Dict[str, Any],
    ) -> HTTPResource:
        """
        Создаёт HTTPResource.
        
        Args:
            definition: Определение ресурса с http конфигом
            variables: Переменные агента
            
        Returns:
            HTTPResource для HTTP запросов
        """
        resolved_config = self._resolve_variable_refs(definition.config, variables)
        config = HTTPResourceConfig.model_validate(resolved_config)
        
        # Резолвим headers отдельно
        resolved_headers = {}
        for key, value in config.headers.items():
            if isinstance(value, str) and value.startswith("@var:"):
                var_name = value[5:]
                resolved_headers[key] = variables.get(var_name, value)
            else:
                resolved_headers[key] = value
        
        logger.debug(
            f"HTTP resource '{definition.resource_id}' loaded: base_url={config.base_url}"
        )
        
        return HTTPResource(
            base_url=config.base_url,
            headers=resolved_headers,
            timeout=config.timeout,
            auth_type=config.auth_type,
            auth_value=config.auth_value,
        )
