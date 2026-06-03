from __future__ import annotations

from typing import cast, override

from core.ai.adapters.openai_compatible import OpenAICompatibleModelCatalogAdapter
from core.ai.models import AIModelRecord, AIRuntimeEndpoint
from core.ai.providers import AICapability
from core.config import BaseSettings
from core.config.llm_openai_compat import resolve_provider_openai_v1_base_url
from core.logging import get_logger
from core.types import JsonObject, JsonValue, require_json_object

logger = get_logger(__name__)

_OPENROUTER_EMBEDDING_MODELS_URL = "https://openrouter.ai/api/v1/embeddings/models"
_OPENROUTER_RERANK_MODELS_URL = "https://openrouter.ai/api/v1/models?output_modalities=rerank"
_OPENROUTER_RERANK_URL = "https://openrouter.ai/api/v1/rerank"


class OpenRouterModelCatalogAdapter(OpenAICompatibleModelCatalogAdapter):
    def __init__(self, settings: BaseSettings | None = None) -> None:
        super().__init__("openrouter", settings)

    def _extract_embedding_model_records(self, payload: JsonValue) -> list[AIModelRecord]:
        payload_object = require_json_object(payload, "openrouter.embedding_models.response")
        data = payload_object.get("data")
        if not isinstance(data, list):
            raise ValueError("openrouter embedding models response: data must be an array")
        return self._records_from_array(
            data,
            provider="openrouter",
            primary_key="id",
            forced_capabilities=(AICapability.EMBEDDING,),
            forced_input_modalities=("text",),
            forced_output_modalities=("embeddings",),
        )

    def _extract_rerank_model_records(self, payload: JsonValue) -> list[AIModelRecord]:
        payload_object = require_json_object(payload, "openrouter.rerank_models.response")
        data = payload_object.get("data")
        if not isinstance(data, list):
            raise ValueError("openrouter rerank models response: data must be an array")
        return self._records_from_array(
            data,
            provider="openrouter",
            primary_key="id",
            forced_capabilities=(AICapability.RERANK,),
            forced_input_modalities=("text",),
            forced_output_modalities=("scores",),
        )

    @override
    def runtime_endpoint(self, capability: AICapability) -> AIRuntimeEndpoint:
        base_url = resolve_provider_openai_v1_base_url(self._settings.llm, self.provider)
        return AIRuntimeEndpoint(
            provider=self.provider,
            capability=capability,
            base_url=base_url,
            endpoint_url=_OPENROUTER_RERANK_URL if capability == AICapability.RERANK else None,
            headers=cast(JsonObject, self.provider_model_list_headers()),
        )

    @override
    async def list_models(self, *, probe_embeddings: bool = True) -> list[AIModelRecord]:
        if not self.is_configured():
            logger.warning("openrouter model provider не настроен")
            return []
        cfg = self._configured_llm_provider()
        if cfg is None:
            raise ValueError("openrouter provider config не настроен")
        records: list[AIModelRecord] = []
        headers = self.provider_model_list_headers()
        payload = await self._fetch_provider_catalog_payload(
            url=self._provider_models_url(cfg),
            headers=headers,
            response_label="openrouter.models.response",
        )
        records.extend(self._extract_provider_model_records(payload, "openrouter"))

        embedding_payload = await self._fetch_provider_catalog_payload(
            url=_OPENROUTER_EMBEDDING_MODELS_URL,
            headers=headers,
            response_label="openrouter.embedding_models.response",
        )
        records.extend(self._extract_embedding_model_records(embedding_payload))

        rerank_payload = await self._fetch_provider_catalog_payload(
            url=_OPENROUTER_RERANK_MODELS_URL,
            headers=headers,
            response_label="openrouter.rerank_models.response",
        )
        records.extend(self._extract_rerank_model_records(rerank_payload))

        merged_records = self._merge_model_records(records)
        if probe_embeddings:
            merged_records = await self._probe_embedding_dimensions(merged_records)
        return merged_records


__all__ = ["OpenRouterModelCatalogAdapter"]
