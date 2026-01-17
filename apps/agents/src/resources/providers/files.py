"""
FilesResourceProvider - провайдер для files ресурсов.
"""

from typing import Any, Dict

from apps.agents.src.models import ResourceDefinition, FilesResourceConfig
from apps.agents.src.resources.providers.base import BaseResourceProvider
from apps.agents.src.resources.wrappers import FilesResource
from core.logging import get_logger

logger = get_logger(__name__)


class FilesResourceProvider(BaseResourceProvider):
    """
    Провайдер для Files ресурсов.
    
    Создаёт FilesResource для работы с S3/MinIO.
    """
    
    def __init__(self, container: Any = None):
        self._container = container
    
    async def resolve(
        self,
        definition: ResourceDefinition,
        variables: Dict[str, Any],
    ) -> FilesResource:
        """
        Создаёт FilesResource.
        
        Args:
            definition: Определение ресурса с files конфигом
            variables: Переменные агента
            
        Returns:
            FilesResource для работы с файлами
        """
        resolved_config = self._resolve_variable_refs(definition.config, variables)
        config = FilesResourceConfig.model_validate(resolved_config)
        
        logger.debug(
            f"Files resource '{definition.resource_id}' loaded: "
            f"bucket={config.bucket}, prefix={config.prefix}"
        )
        
        return FilesResource(
            bucket=config.bucket,
            prefix=config.prefix,
            endpoint_url=config.endpoint_url,
            access_key_id=config.access_key_id,
            secret_access_key=config.secret_access_key,
            region=config.region,
            container=self._container,
        )
