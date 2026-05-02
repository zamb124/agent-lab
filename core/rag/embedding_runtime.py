"""
Итоговый ``base_url`` эмбеддингов для PgVectorProvider / EmbeddingService из Pydantic-конфига.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, Literal

from core.config.llm_openai_compat import resolve_llm_openai_v1_base_url
from core.config.openai_v1_base_url import normalize_openai_v1_base_url

if TYPE_CHECKING:
    from core.config.models import EmbeddingConfig, LLMConfig, ProviderLitserveConfig


@dataclass(frozen=True)
class RagEmbeddingRuntime:
    """Поля из ``rag.embedding`` + вычисленный корень OpenAI-совместимого API (``…/v1``)."""

    provider: Literal["openrouter", "provider_litserve"]
    model: str
    dimension: int
    base_url: str
    mrl_output_dimension: int | None = None


def resolve_rag_embedding_runtime(
    embedding: "EmbeddingConfig",
    llm: "LLMConfig",
    provider_litserve: "ProviderLitserveConfig",
) -> RagEmbeddingRuntime:
    """
    ``embedding.api`` + источник ``base_url``:

    - ``openrouter``: ``api.base_url`` или корень из ``llm`` (активный ``llm.provider``).
    - ``provider_litserve``: ``api.base_url`` при непустом значении, иначе
      ``provider_litserve.resolve_openai_v1_base_url()`` из настроек процесса LitServe.
    """
    api = embedding.api

    if embedding.provider == "openrouter":
        explicit = api.base_url
        if explicit is not None and str(explicit).strip():
            bu = normalize_openai_v1_base_url(str(explicit).strip())
        else:
            bu = resolve_llm_openai_v1_base_url(llm)
    elif embedding.provider == "provider_litserve":
        explicit = api.base_url
        if explicit is not None and str(explicit).strip():
            bu = normalize_openai_v1_base_url(str(explicit).strip())
        else:
            bu = provider_litserve.resolve_openai_v1_base_url()
    else:
        raise ValueError(f"Неизвестный rag.embedding.provider: {embedding.provider}")

    return RagEmbeddingRuntime(
        provider=embedding.provider,
        model=api.model,
        dimension=api.dimension,
        base_url=bu,
        mrl_output_dimension=api.mrl_output_dimension,
    )


def build_rag_embedding_runtime_dict(
    embedding: "EmbeddingConfig",
    llm: "LLMConfig",
    provider_litserve: "ProviderLitserveConfig",
) -> dict[str, Any]:
    """Тот же контракт, что у ``RagEmbeddingRuntime``, в виде словаря."""
    return asdict(resolve_rag_embedding_runtime(embedding, llm, provider_litserve))
