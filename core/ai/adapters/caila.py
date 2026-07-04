from __future__ import annotations

from typing import override

from core.ai.adapters.openai_compatible import OpenAICompatibleModelCatalogAdapter
from core.ai.models import AIModelRecord
from core.ai.providers import AICapability
from core.config import BaseSettings
from core.logging import get_logger
from core.types import JsonObject, JsonValue, require_json_object

logger = get_logger(__name__)

_CAILA_OPENAI_ENDPOINT = "/api/openai/v1/chat/completions"
_CAILA_OPENAI_API = "OPENAI"


def _caila_capabilities(model_id: str) -> tuple[AICapability, ...]:
    model_id_lower = model_id.lower()
    capabilities: set[AICapability] = set()
    if "image" in model_id_lower or "vision" in model_id_lower:
        capabilities.add(AICapability.LLM_VISION)
    if (
        "embedding" in model_id_lower
        or "embed" in model_id_lower
        or "bge-m3" in model_id_lower
        or "e5-" in model_id_lower
    ):
        capabilities.add(AICapability.EMBEDDING)
        return tuple(capabilities)
    capabilities.update(
        {
            AICapability.LLM_CHAT,
            AICapability.LLM_SUMMARIZE,
            AICapability.LLM_FORMAT_MARKDOWN,
            AICapability.LLM_CODEGEN,
        }
    )
    return tuple(cap for cap in AICapability if cap in capabilities)


class CailaModelCatalogAdapter(OpenAICompatibleModelCatalogAdapter):
    def __init__(self, settings: BaseSettings | None = None) -> None:
        super().__init__("caila", settings)

    @override
    async def list_models(self, *, probe_embeddings: bool = True) -> list[AIModelRecord]:
        if not self.is_configured():
            logger.warning("caila model provider не настроен")
            return []
        cfg = self._configured_llm_provider()
        if cfg is None:
            raise ValueError("caila provider config не настроен")
        payload = await self._fetch_provider_catalog_payload(
            url=self._provider_models_url(cfg),
            headers=self.provider_model_list_headers(),
            response_label="caila.models.response",
        )
        if not isinstance(payload, list):
            raise ValueError("caila models response должен быть массивом")
        records = self._extract_caila_model_records(payload)
        merged_records = self._merge_model_records(records)
        if probe_embeddings:
            merged_records = await self._probe_embedding_dimensions(merged_records)
        logger.info("caila: получено %d моделей", len(merged_records))
        return merged_records

    def _extract_caila_model_records(self, items: list[JsonValue]) -> list[AIModelRecord]:
        records: list[AIModelRecord] = []
        for idx, raw_item in enumerate(items):
            item = require_json_object(raw_item, f"caila.models[{idx}]")
            if not self._caila_item_has_openai_endpoint(item):
                continue
            record = self._caila_record_from_item(item)
            if record is not None:
                records.append(record)
        return records

    def _caila_item_has_openai_endpoint(self, item: JsonObject) -> bool:
        endpoints = item.get("endpoints")
        if not isinstance(endpoints, list) or not endpoints:
            return False
        apis = item.get("apis")
        if not isinstance(apis, list):
            return False
        return any(
            isinstance(api, dict) and api.get("format") == _CAILA_OPENAI_API
            for api in apis
        )

    def _caila_record_from_item(self, item: JsonObject) -> AIModelRecord | None:
        model_id = self._json_str(item.get("id"))
        if model_id is None:
            return None
        capabilities = _caila_capabilities(model_id)
        return AIModelRecord(
            model_id=model_id,
            provider="caila",
            capabilities=capabilities,
            input_modalities=(),
            output_modalities=(),
            supported_parameters=(),
            context_length=None,
            created=None,
            native_dimension=None,
            storage_dimension=None,
            mrl_output_dimension=None,
            supports_tools=False,
            supports_structured_output=False,
            is_free=None,
            free_reason=None,
            metadata_status="discovered",
            raw=item,
        )


__all__ = ["CailaModelCatalogAdapter"]
