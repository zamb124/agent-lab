"""
LLMResourceProvider - провайдер для llm ресурсов.
"""

from typing import Any

from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.models import LLMResourceConfig, ResourceDefinition
from apps.flows.src.resources.providers.base import BaseResourceProvider
from apps.flows.src.resources.wrappers.llm_resource import LLMResource
from core.logging import get_logger

logger = get_logger(__name__)


class LLMResourceProvider(BaseResourceProvider):
    """
    Провайдер для LLM ресурсов.

    Создаёт LLMResource для генерации текста.
    """

    def __init__(self, container: FlowRuntimeContainer):
        self.container = container

    async def resolve(
        self,
        definition: ResourceDefinition,
        variables: dict[str, Any],
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
        provider, model = config.required_identity()
        temperature = config.temperature if config.temperature is not None else 0.7

        logger.debug(
            f"LLM resource '{definition.resource_id}' loaded: "
            f"provider={provider}, model={model}"
        )

        return LLMResource(
            provider=provider,
            model=model,
            fallback_models=config.fallback_models,
            temperature=temperature,
            max_tokens=config.max_tokens,
            top_p=config.top_p,
            top_k=config.top_k,
            frequency_penalty=config.frequency_penalty,
            presence_penalty=config.presence_penalty,
            seed=config.seed,
            reasoning_effort=config.reasoning_effort,
            api_key=config.api_key,
            base_url=config.base_url,
            folder_id=config.folder_id,
            extra_request_body=config.extra_request_body,
            extra_request_headers=config.extra_request_headers,
            container=self.container,
        )
