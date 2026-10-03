from __future__ import annotations

from typing import override

from core.ai.adapters.catalog_base import BaseModelCatalogAdapter, string_headers_json
from core.ai.models import AIModelRecord, AIRuntimeEndpoint
from core.ai.providers import PROVIDER_LITSERVE, AICapability


class ProviderLitserveModelCatalogAdapter(BaseModelCatalogAdapter):
    provider: str = PROVIDER_LITSERVE

    @override
    def embedding_probe_timeout_seconds(self) -> float:
        return 60.0

    @override
    def runtime_endpoint(self, capability: AICapability) -> AIRuntimeEndpoint:
        base_url = self._provider_litserve_openai_v1_base_url()
        endpoint_url = None
        if capability == AICapability.RERANK:
            endpoint_url = f"{base_url.rstrip('/')}/rerank"
        return AIRuntimeEndpoint(
            provider=self.provider,
            capability=capability,
            base_url=base_url,
            endpoint_url=endpoint_url,
            headers=string_headers_json(self._provider_litserve_model_list_headers()),
        )

    @override
    async def list_models(self, *, probe_embeddings: bool = True) -> list[AIModelRecord]:
        if not self.is_configured():
            raise ValueError('provider_litserve model provider is not configured')
        payload = await self._fetch_provider_catalog_payload(
            url=f"{self._provider_litserve_openai_v1_base_url().rstrip('/')}/models",
            headers=self._provider_litserve_model_list_headers(),
            response_label="provider_litserve.models.response",
        )
        records = self._extract_provider_model_records(payload, self.provider)
        if probe_embeddings:
            records = await self._probe_embedding_dimensions(records)
        return records


__all__ = ["ProviderLitserveModelCatalogAdapter"]
