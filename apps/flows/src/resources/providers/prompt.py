"""
PromptResourceProvider - провайдер для prompt ресурсов.
"""

from typing import Any, Dict

from apps.flows.src.models import ResourceDefinition, PromptResourceConfig
from apps.flows.src.resources.providers.base import BaseResourceProvider
from apps.flows.src.resources.wrappers import PromptResource
from core.logging import get_logger

logger = get_logger(__name__)


class PromptResourceProvider(BaseResourceProvider):
    """
    Провайдер для Prompt ресурсов.
    
    Создаёт PromptResource для работы с шаблонами промптов.
    """
    
    async def resolve(
        self,
        definition: ResourceDefinition,
        variables: Dict[str, Any],
    ) -> PromptResource:
        """
        Создаёт PromptResource.
        
        Args:
            definition: Определение ресурса с prompt конфигом
            variables: Переменные агента
            
        Returns:
            PromptResource для работы с шаблонами
        """
        config = PromptResourceConfig.model_validate(definition.config)
        
        # Мержим дефолтные переменные ресурса с переменными агента
        merged_variables = {**config.variables, **variables}
        
        logger.debug(
            f"Prompt resource '{definition.resource_id}' loaded"
        )
        
        return PromptResource(
            template=config.template,
            variables=merged_variables,
        )
