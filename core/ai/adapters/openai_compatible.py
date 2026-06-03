from __future__ import annotations

from typing import override

from core.ai.adapters.catalog_base import BaseModelCatalogAdapter
from core.ai.models import AIModelRecord
from core.ai.providers import OPENAI_COMPATIBLE_LLM_PROVIDER_SLUGS
from core.config import BaseSettings
from core.logging import get_logger

logger = get_logger(__name__)


class OpenAICompatibleModelCatalogAdapter(BaseModelCatalogAdapter):
    provider: str

    def __init__(self, provider: str, settings: BaseSettings | None = None) -> None:
        if provider not in OPENAI_COMPATIBLE_LLM_PROVIDER_SLUGS:
            raise ValueError(f"unknown OpenAI-compatible model catalog provider: {provider!r}")
        self.provider = provider
        super().__init__(settings)

    @override
    async def list_models(self, *, probe_embeddings: bool = True) -> list[AIModelRecord]:
        if not self.is_configured():
            logger.warning("%s model provider не настроен", self.provider)
            return []
        cfg = self._configured_llm_provider()
        if cfg is None:
            raise ValueError(f"{self.provider} provider config не настроен")
        payload = await self._fetch_provider_catalog_payload(
            url=self._provider_models_url(cfg),
            headers=self.provider_model_list_headers(),
            response_label=f"{self.provider}.models.response",
        )
        records = self._extract_provider_model_records(payload, self.provider)
        if probe_embeddings:
            records = await self._probe_embedding_dimensions(records)
        logger.info("%s: получено %d моделей", self.provider, len(records))
        return records


__all__ = ["OpenAICompatibleModelCatalogAdapter"]
