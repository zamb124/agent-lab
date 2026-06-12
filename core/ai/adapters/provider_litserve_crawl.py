from __future__ import annotations

from typing import cast, override

from core.ai.adapters.catalog_base import BaseModelCatalogAdapter
from core.ai.models import AIModelRecord, AIRuntimeEndpoint
from core.ai.providers import PROVIDER_LITSERVE_CRAWL, AICapability
from core.rag.openai_http_contracts import PROVIDER_LITSERVE_PLACEHOLDER_BEARER
from core.types import JsonObject


class ProviderLitserveCrawlModelCatalogAdapter(BaseModelCatalogAdapter):
    provider: str = PROVIDER_LITSERVE_CRAWL

    @override
    def runtime_endpoint(self, capability: AICapability) -> AIRuntimeEndpoint:
        base_url = self._provider_litserve_crawl_openai_v1_base_url()
        return AIRuntimeEndpoint(
            provider=self.provider,
            capability=capability,
            base_url=base_url,
            endpoint_url=None,
            headers=cast(JsonObject, self._provider_litserve_crawl_model_list_headers()),
        )

    @override
    async def list_models(self, *, probe_embeddings: bool = True) -> list[AIModelRecord]:
        _ = probe_embeddings
        if not self.is_configured():
            return []
        payload = await self._fetch_provider_catalog_payload(
            url=f"{self._provider_litserve_crawl_openai_v1_base_url().rstrip('/')}/models",
            headers=self._provider_litserve_crawl_model_list_headers(),
            response_label="provider_litserve_crawl.models.response",
        )
        return self._extract_provider_model_records(payload, self.provider)

    @staticmethod
    def _provider_litserve_crawl_model_list_headers() -> dict[str, str]:
        return {
            "Authorization": f"Bearer {PROVIDER_LITSERVE_PLACEHOLDER_BEARER}",
            "Content-Type": "application/json",
        }

    def _provider_litserve_crawl_openai_v1_base_url(self) -> str:
        return self._settings.provider_litserve.resolve_openai_v1_base_url()


__all__ = ["ProviderLitserveCrawlModelCatalogAdapter"]
