"""
Итоговый ``base_url`` эмбеддингов для PgVectorProvider / EmbeddingService из Pydantic-конфига.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.ai_provider_catalog import (
    PROVIDER_LITSERVE,
    AICapability,
    validate_platform_provider_for_capability,
)
from core.config.llm_openai_compat import resolve_provider_openai_v1_base_url
from core.config.openai_v1_base_url import normalize_openai_v1_base_url

if TYPE_CHECKING:
    from core.config.models import EmbeddingConfig, LLMConfig, ProviderLitserveConfig


@dataclass(frozen=True)
class RagEmbeddingRuntime:
    """Поля из ``rag.embedding`` + вычисленный корень OpenAI-совместимого API (``…/v1``)."""

    provider: str
    model: str
    dimension: int
    base_url: str
    mrl_output_dimension: int | None = None
    extra_request_headers: dict[str, str] | None = None


def resolve_rag_embedding_runtime(
    embedding: "EmbeddingConfig",
    llm: "LLMConfig",
    provider_litserve: "ProviderLitserveConfig",
) -> RagEmbeddingRuntime:
    """
    ``embedding.api`` + источник ``base_url``:

    - OpenAI-compatible provider: ``api.base_url`` или корень из соответствующего ``llm.<provider>``.
    - ``provider_litserve``: ``api.base_url`` при непустом значении, иначе
      ``provider_litserve.resolve_openai_v1_base_url()`` из настроек процесса LitServe.
    """
    api = embedding.api
    provider = validate_platform_provider_for_capability(embedding.provider, AICapability.EMBEDDING)

    if provider == PROVIDER_LITSERVE:
        explicit = api.base_url
        if explicit is not None and str(explicit).strip():
            bu = normalize_openai_v1_base_url(str(explicit).strip())
        else:
            bu = provider_litserve.resolve_openai_v1_base_url()
    else:
        explicit = api.base_url
        if explicit is not None and str(explicit).strip():
            bu = normalize_openai_v1_base_url(str(explicit).strip())
        else:
            bu = resolve_provider_openai_v1_base_url(llm, provider)

    return RagEmbeddingRuntime(
        provider=provider,
        model=api.model,
        dimension=api.dimension,
        base_url=bu,
        mrl_output_dimension=api.mrl_output_dimension,
    )
