from __future__ import annotations

from typing import cast, override

from core.ai.adapters.openai_compatible import OpenAICompatibleModelCatalogAdapter
from core.ai.models import AIModelRecord, AIRuntimeEndpoint, ArtificialAnalysisIndices
from core.ai.providers import AICapability
from core.ai.scoring import normalize_aa_model_slug
from core.config import BaseSettings
from core.config.llm_openai_compat import resolve_provider_openai_v1_base_url
from core.types import JsonObject, JsonValue, require_json_object

_OPENROUTER_EMBEDDING_MODELS_URL = "https://openrouter.ai/api/v1/embeddings/models"
_OPENROUTER_RERANK_MODELS_URL = "https://openrouter.ai/api/v1/models?output_modalities=rerank"
_OPENROUTER_RERANK_URL = "https://openrouter.ai/api/v1/rerank"
_OPENROUTER_BENCHMARKS_URL = "https://openrouter.ai/api/v1/benchmarks"


def _aa_optional_index(value: JsonValue | None, *, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be numeric")
    return float(value)


def parse_artificial_analysis_payload(payload: JsonValue) -> dict[str, ArtificialAnalysisIndices]:
    payload_object = require_json_object(payload, "openrouter.benchmarks.artificial_analysis")
    data = payload_object.get("data")
    if not isinstance(data, list):
        raise ValueError("openrouter benchmarks response: data must be an array")
    indices: dict[str, ArtificialAnalysisIndices] = {}
    for idx, raw_item in enumerate(data):
        item = require_json_object(raw_item, f"openrouter.benchmarks.data[{idx}]")
        slug_raw = item.get("model_permaslug")
        if not isinstance(slug_raw, str) or not slug_raw.strip():
            raise ValueError(f"openrouter.benchmarks.data[{idx}].model_permaslug is required")
        intelligence = item.get("intelligence_index")
        if intelligence is None:
            continue
        if isinstance(intelligence, bool) or not isinstance(intelligence, (int, float)):
            raise ValueError(
                f"openrouter.benchmarks.data[{idx}].intelligence_index must be numeric"
            )
        slug = normalize_aa_model_slug(slug_raw)
        parsed = ArtificialAnalysisIndices(
            intelligence_index=float(intelligence),
            coding_index=_aa_optional_index(
                item.get("coding_index"),
                field_name=f"openrouter.benchmarks.data[{idx}].coding_index",
            ),
            agentic_index=_aa_optional_index(
                item.get("agentic_index"),
                field_name=f"openrouter.benchmarks.data[{idx}].agentic_index",
            ),
            model_permaslug=slug_raw.strip(),
        )
        existing = indices.get(slug)
        if existing is not None and existing.intelligence_index != parsed.intelligence_index:
            raise ValueError(
                f"openrouter.benchmarks: duplicate model_permaslug {slug!r} with different intelligence_index"
            )
        indices[slug] = parsed
    return indices


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
            raise ValueError('openrouter model provider is not configured')
        cfg = self._configured_llm_provider()
        if cfg is None:
            raise ValueError('openrouter provider config is not configured')
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

    async def list_artificial_analysis(self) -> dict[str, ArtificialAnalysisIndices]:
        if not self.is_configured():
            raise ValueError('openrouter model provider is not configured')
        payload = await self._fetch_provider_catalog_payload(
            url=_OPENROUTER_BENCHMARKS_URL,
            headers=self.provider_model_list_headers(),
            response_label="openrouter.benchmarks.artificial_analysis",
            params={"source": "artificial-analysis"},
        )
        return parse_artificial_analysis_payload(payload)


__all__ = ["OpenRouterModelCatalogAdapter", "parse_artificial_analysis_payload"]
