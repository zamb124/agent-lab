from __future__ import annotations

from typing import override

from core.ai.adapters.openai_compatible import OpenAICompatibleModelCatalogAdapter
from core.ai.models import AIModelRecord
from core.ai.providers import AICapability
from core.config import BaseSettings
from core.logging import get_logger
from core.types import JsonValue

logger = get_logger(__name__)

_HUGGINGFACE_FEATURE_EXTRACTION_MODELS_URL = (
    "https://huggingface.co/api/models"
    "?inference_provider=hf-inference&pipeline_tag=feature-extraction&limit=40"
)


class HuggingFaceModelCatalogAdapter(OpenAICompatibleModelCatalogAdapter):
    def __init__(self, settings: BaseSettings | None = None) -> None:
        super().__init__("huggingface", settings)

    def _extract_feature_extraction_model_records(
        self,
        payload: JsonValue,
    ) -> list[AIModelRecord]:
        if not isinstance(payload, list):
            raise ValueError("huggingface feature-extraction models response must be an array")
        return self._records_from_array(
            payload,
            provider="huggingface",
            primary_key="id",
            forced_capabilities=(AICapability.EMBEDDING,),
            forced_input_modalities=("text",),
            forced_output_modalities=("embeddings",),
        )

    @override
    async def list_models(self, *, probe_embeddings: bool = True) -> list[AIModelRecord]:
        if not self.is_configured():
            logger.warning("huggingface model provider не настроен")
            return []
        cfg = self._configured_llm_provider()
        if cfg is None:
            raise ValueError("huggingface provider config не настроен")
        headers = self.provider_model_list_headers()
        payload = await self._fetch_provider_catalog_payload(
            url=self._provider_models_url(cfg),
            headers=headers,
            response_label="huggingface.models.response",
        )
        records = self._extract_provider_model_records(payload, "huggingface")

        feature_payload = await self._fetch_provider_catalog_payload(
            url=_HUGGINGFACE_FEATURE_EXTRACTION_MODELS_URL,
            headers=headers,
            response_label="huggingface.feature_extraction_models.response",
        )
        records.extend(self._extract_feature_extraction_model_records(feature_payload))

        merged_records = self._merge_model_records(records)
        if probe_embeddings:
            merged_records = await self._probe_embedding_dimensions(merged_records)
        return merged_records


__all__ = ["HuggingFaceModelCatalogAdapter"]
