"""
ResourceResolver - резолвинг ресурсов flow.

Поддерживает:
- Inline ресурсы (type + config)
- Shared ресурсы из БД (resource_id)
- Переопределение shared ресурсов (resource_id + config)
- Иерархию: flow > skill > node
"""

from typing import Any, Dict, Optional

from apps.flows.src.db import ResourceRepository
from apps.flows.src.models import (
    ResourceType,
    ResourceDefinition,
    ResourceReference,
)
from apps.flows.src.resources.merge import (
    merge_flow_skill_node_resource_maps,
    merge_shared_definition_config_with_patch,
)
from apps.flows.src.resources.providers import (
    BaseResourceProvider,
    CodeResourceProvider,
    RAGResourceProvider,
    LLMResourceProvider,
    HTTPResourceProvider,
    FilesResourceProvider,
    CacheResourceProvider,
    PromptResourceProvider,
    SecretResourceProvider,
)
from core.logging import get_logger

logger = get_logger(__name__)


class ResourceResolver:
    """
    Резолвит ресурсы для нод flow.
    
    Порядок приоритета: node > skill > flow
    """
    
    def __init__(
        self,
        repository: ResourceRepository,
        container: Any = None,
    ):
        self.repository = repository
        self._container = container
        
        # Провайдеры для каждого типа
        self._providers: Dict[ResourceType, BaseResourceProvider] = {
            ResourceType.CODE: CodeResourceProvider(),
            ResourceType.RAG: RAGResourceProvider(container),
            ResourceType.LLM: LLMResourceProvider(container),
            ResourceType.HTTP: HTTPResourceProvider(),
            ResourceType.FILES: FilesResourceProvider(container),
            ResourceType.CACHE: CacheResourceProvider(container),
            ResourceType.PROMPT: PromptResourceProvider(),
            ResourceType.SECRET: SecretResourceProvider(container),
        }
    
    async def resolve_for_node(
        self,
        flow_resources: Optional[Dict[str, ResourceReference]] = None,
        skill_resources: Optional[Dict[str, ResourceReference]] = None,
        node_resources: Optional[Dict[str, ResourceReference]] = None,
        variables: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Резолвит все ресурсы для конкретной ноды.
        
        Приоритет: node > skill > flow
        
        Args:
            flow_resources: Ресурсы уровня flow (из FlowConfig.resources)
            skill_resources: Ресурсы skill
            node_resources: Ресурсы ноды
            variables: Переменные для резолвинга @var:
            
        Returns:
            Dict[resource_id, wrapper] для добавления в namespace
        """
        flow_resources = flow_resources or {}
        skill_resources = skill_resources or {}
        node_resources = node_resources or {}
        variables = variables or {}
        
        merged = merge_flow_skill_node_resource_maps(
            flow_resources, skill_resources, node_resources
        )
        
        # Резолвим каждый ресурс
        resolved: Dict[str, Any] = {}
        
        for resource_id, ref in merged.items():
            try:
                if isinstance(ref, dict):
                    ref = ResourceReference.model_validate(ref)
                resolved[resource_id] = await self._resolve_reference(
                    resource_id=resource_id,
                    ref=ref,
                    variables=variables,
                )
            except Exception as e:
                logger.error(f"Failed to resolve resource '{resource_id}': {e}")
                raise
        
        return resolved
    
    async def _resolve_reference(
        self,
        resource_id: str,
        ref: ResourceReference,
        variables: Dict[str, Any],
    ) -> Any:
        """
        Резолвит одну ссылку на ресурс.
        
        Args:
            resource_id: ID ресурса (ключ в dict)
            ref: Ссылка на ресурс
            variables: Переменные для резолвинга
            
        Returns:
            Wrapper объект
        """
        if ref.is_inline:
            # Inline ресурс - создаём definition из ref
            definition = ResourceDefinition(
                resource_id=resource_id,
                type=ref.type,
                name=ref.name,
                description=ref.description,
                config=ref.config,
            )
        else:
            # Shared ресурс - загружаем из БД
            definition = await self.repository.get(ref.resource_id)
            if definition is None:
                raise ValueError(
                    f"Shared resource '{ref.resource_id}' not found in database"
                )
            
            # Применяем override если есть
            if ref.config:
                merged_config = merge_shared_definition_config_with_patch(
                    definition.type,
                    definition.config,
                    ref.config,
                )
                definition = ResourceDefinition(
                    resource_id=definition.resource_id,
                    type=definition.type,
                    name=definition.name,
                    description=definition.description,
                    config=merged_config,
                    tags=definition.tags,
                    permission=definition.permission,
                )
        
        # Получаем провайдер и резолвим
        provider = self._providers.get(definition.type)
        if provider is None:
            raise ValueError(f"Unknown resource type: {definition.type}")
        
        return await provider.resolve(definition, variables)
    
    async def resolve_single(
        self,
        ref: ResourceReference,
        variables: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Резолвит один ресурс.
        
        Args:
            ref: Ссылка на ресурс
            variables: Переменные
            
        Returns:
            Wrapper объект
        """
        return await self._resolve_reference(
            resource_id="_single",
            ref=ref,
            variables=variables or {},
        )


__all__ = ["ResourceResolver"]
