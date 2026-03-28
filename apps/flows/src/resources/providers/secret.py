"""
SecretResourceProvider - провайдер для secret ресурсов.
"""

from typing import Any, Dict

from apps.flows.src.models import ResourceDefinition, SecretResourceConfig
from apps.flows.src.resources.providers.base import BaseResourceProvider
from core.variables import VarResolver
from core.logging import get_logger

logger = get_logger(__name__)


class SecretResourceProvider(BaseResourceProvider):
    """
    Провайдер для Secret ресурсов.
    
    Резолвит секреты из переменных и возвращает значение.
    """
    
    def __init__(self, container: Any = None):
        self._container = container
    
    async def resolve(
        self,
        definition: ResourceDefinition,
        variables: Dict[str, Any],
    ) -> str:
        """
        Резолвит секрет из переменных.
        
        Args:
            definition: Определение ресурса с secret конфигом
            variables: Переменные агента
            
        Returns:
            Значение секрета
        """
        config = SecretResourceConfig.model_validate(definition.config)
        
        key = config.key
        
        # Резолвим @var: ссылку
        if key.startswith("@var:"):
            value = VarResolver.resolve_ref(key, variables)
            logger.debug(f"Secret resource '{definition.resource_id}' resolved from variables")
            if not isinstance(value, str):
                return str(value)
            return value
        
        # Если не @var:, возвращаем как есть (прямое значение)
        return key
