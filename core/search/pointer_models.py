"""Контракты pointer-index (vector-only) для runet search.

Includes config models for:
  - Phase 1:  vector_pointer index mode, study strategies (§4.10, §4.11)
  - Phase 1b: halfvec MRL-512 pilot (§4.8, §15)
  - Phase 1c: SPLADE sparse neural gate (§4.3.5)
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Literal

from pydantic import ConfigDict, Field

from core.models import StrictBaseModel
from core.types import JsonObject

VectorPointerDocType = Literal["vector_pointer"]
IndexStudyStrategy = Literal["lexical", "split_embed", "llm_embed", "hybrid_study"]
VectorRole = Literal["global", "section", "salient"]
RunetIndexMode = Literal["vector_pointer", "chunk_mirror"]

POINTER_INDEX_CONTENT_STUB: str = "."

INDEX_STUDY_STRATEGIES: tuple[IndexStudyStrategy, ...] = (
    "lexical",
    "split_embed",
    "llm_embed",
    "hybrid_study",
)


class VectorPointerMetadata(StrictBaseModel):
    """Metadata index-vector row для doc_type=vector_pointer (§5.1)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    doc_type: VectorPointerDocType = "vector_pointer"
    source_url: str = Field(..., min_length=1)
    canonical_url: str | None = None
    vector_role: VectorRole = "global"
    index_study_strategy: IndexStudyStrategy = "lexical"
    salient_terms: list[str] = Field(default_factory=list)
    section_titles: list[str] = Field(default_factory=list)
    section_title: str | None = None
    heading_trail: list[str] = Field(default_factory=list)
    html_title: str | None = None
    meta_description: str | None = None
    page_summary: str | None = None
    extract_content_hash: str | None = None
    indexed_at: datetime | None = None
    search_index_id: str | None = None


class HalfVecPilotConfig(StrictBaseModel):
    """Phase 1b: MRL-512 + halfvec A/B eval pilot (§4.8, §15).

    Activating this pilot requires a DDL migration to change the vector column
    type from vector(1024) to halfvec(512).  The config here tracks the intent
    and shadow namespace for eval before the DDL gate is met.

    DoD gate: url_recall@10 not worse than -3pp vs 1024d float baseline.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    enabled: bool = False
    mrl_dimension: int = Field(default=512, ge=64, le=1024)
    shadow_namespace_suffix: str = Field(
        default="runet:eval:halfvec512",
        min_length=1,
        max_length=128,
    )
    ddl_migrated: bool = False


class RunetResearchPoolConfig(StrictBaseModel):
    """Pool caps для research orchestrator (маппинг InfoSeeker pool_config.yaml)."""

    max_urls: int = Field(default=10, ge=1, le=40)
    max_depth: int = Field(default=2, ge=0, le=5)
    max_fetch_ms: int = Field(default=30_000, ge=1_000, le=300_000)
    fetch_concurrency: int = Field(default=5, ge=1, le=40)
    browser_pool_size: int = Field(default=3, ge=1, le=10)
    per_url_timeout_ms: int = Field(default=8_000, ge=1_000, le=60_000)
    max_passages_per_url: int = Field(default=40, ge=1, le=200)
    max_passages_total: int = Field(default=200, ge=1, le=500)
    rerank_top_k: int = Field(default=10, ge=1, le=50)
    max_passage_tokens: int = Field(default=400, ge=50, le=2000)
    in_page_embed_threshold_tokens: int = Field(default=8000, ge=1000, le=100_000)
    ephemeral_rag_fallback: bool = False


class SparseEvalGate(StrictBaseModel):
    """Phase 1c gate criteria for SPLADE sparse neural pilot (§4.3.5).

    Sparse neural is activated only when BOTH conditions are met on the
    RU rare-term eval subset (≥20 queries):
      1. url_recall@10 < rare_term_url_recall_threshold
      2. vocabulary_mismatch_rate > vocabulary_mismatch_threshold
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    rare_term_url_recall_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    vocabulary_mismatch_threshold: float = Field(default=0.15, ge=0.0, le=1.0)


class SparsePilotConfig(StrictBaseModel):
    """Phase 1c: SPLADE sparse neural pilot (gated, §4.3.5, §4.3.6).

    Storage: sparse weights are stored in metadata JSONB (no DDL change).
    The third RRF channel (dense + FTS + sparse) is enabled only when both
    eval gate criteria from SparseEvalGate are passed on the RU rare-term
    query subset.

    Inference: naver/splade-v3 or efficient-splade via LitServe endpoint.
    DoD: rare_term_url_recall@10 +5pp vs Phase 1 alone.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    enabled: bool = False
    litserve_model: str = Field(
        default="naver/splade-v3",
        min_length=1,
        max_length=128,
    )
    max_sparse_weights: int = Field(default=300, ge=16, le=1024)
    rrf_sparse_weight: float = Field(default=1.0, ge=0.1, le=10.0)
    metadata_key: str = Field(default="sparse_weights", min_length=1, max_length=64)
    eval_gate: SparseEvalGate = Field(default_factory=SparseEvalGate)
    shadow_namespace_suffix: str = Field(
        default="runet:eval:sparse",
        min_length=1,
        max_length=128,
    )


def is_sparse_gate_met(
    *,
    gate: SparseEvalGate,
    rare_term_url_recall: float,
    vocabulary_mismatch_rate: float,
) -> bool:
    """Return True only when both Phase 1c gate conditions are satisfied."""
    return (
        rare_term_url_recall < gate.rare_term_url_recall_threshold
        and vocabulary_mismatch_rate > gate.vocabulary_mismatch_threshold
    )


class SalientTermsConfig(StrictBaseModel):
    """Salient term extraction for pointer-index (§4.2)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    backend: Literal["local", "keybert"] = "keybert"
    fallback_to_local: bool = True
    litserve_base_url: str | None = Field(
        default=None,
        description="Override provider_litserve OpenAI v1 base URL for KeyBERT.",
    )
    keybert_model: str | None = Field(
        default=None,
        description="Override KeyBERT OpenAI model id; default from provider_litserve.infra.",
    )
    keybert_top_n: int = Field(default=50, ge=8, le=256)
    keybert_use_mmr: bool = True
    keybert_diversity: float = Field(default=0.7, ge=0.0, le=1.0)
    max_input_chars: int = Field(default=50_000, ge=1000, le=200_000)


class RunetPointerConfig(StrictBaseModel):
    """Конфиг runet pointer-index (§10).

    Fields:
      Phase 1:  index_mode, study_strategy, vectors, debug
      Phase 1b: halfvec_pilot
      Phase 1c: sparse_pilot
    """

    index_mode: RunetIndexMode = "vector_pointer"
    index_study_strategy: IndexStudyStrategy = "lexical"
    index_study_strategies_eval: list[IndexStudyStrategy] = Field(
        default_factory=lambda: ["lexical", "split_embed", "hybrid_study"],
    )
    persist_index_content_debug: bool = False
    index_content_stub: str = Field(default=POINTER_INDEX_CONTENT_STUB, min_length=1, max_length=64)
    max_vectors_per_url: int = Field(default=12, ge=1, le=32)
    salient_terms_max: int = Field(default=80, ge=8, le=256)
    salient_terms: SalientTermsConfig = Field(default_factory=SalientTermsConfig)
    discovery_limit: int = Field(default=10, ge=1, le=50)
    research: RunetResearchPoolConfig = Field(default_factory=RunetResearchPoolConfig)
    halfvec_pilot: HalfVecPilotConfig = Field(default_factory=HalfVecPilotConfig)
    sparse_pilot: SparsePilotConfig = Field(default_factory=SparsePilotConfig)


def is_vector_pointer_metadata(metadata: JsonObject) -> bool:
    doc_type = metadata.get("doc_type")
    return doc_type == "vector_pointer"


def resolve_index_content_stub(
    *,
    persist_debug: bool,
    debug_preview: str | None,
    stub: str = POINTER_INDEX_CONTENT_STUB,
) -> str:
    if persist_debug and debug_preview and debug_preview.strip():
        return debug_preview.strip()[:4000]
    return stub
