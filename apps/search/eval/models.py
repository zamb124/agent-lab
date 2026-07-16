"""Runet search eval harness — модели golden set и arms."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import ConfigDict, Field

from core.models import StrictBaseModel

EvalQueryType = Literal[
    "general",
    "rare_term",
    "paraphrase",
    "short_ru",
    "news",
    "multi_hop",
    "long_doc",
]
EvalRelevanceGrade = Literal[0, 1, 2, 3]


class EvalUrlRelevance(StrictBaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    url: str = Field(..., min_length=1)
    grade: EvalRelevanceGrade = Field(..., ge=0, le=3)
    section_title: str | None = None


class EvalQuery(StrictBaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    query_id: str = Field(..., min_length=1, max_length=128)
    query: str = Field(..., min_length=1, max_length=500)
    query_type: EvalQueryType = "general"
    relevances: list[EvalUrlRelevance] = Field(..., min_length=1)


class EvalRetrievedUrl(StrictBaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    url: str
    rank: int = Field(..., ge=1)
    score: float = Field(default=0.0, ge=0.0)
    document_id: str | None = None


class EvalArmRunConfig(StrictBaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    arm_id: str = Field(..., min_length=1, max_length=128)
    namespace_id: str = Field(..., min_length=1, max_length=255)
    arm_kind: Literal["chunking", "index_study"] = "chunking"
    notes: str = ""


class EvalQueryResult(StrictBaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    query_id: str
    query_type: EvalQueryType
    retrieved: list[EvalRetrievedUrl]
    ideal_url_found: bool
    first_ideal_rank: int | None = None
    ndcg_at_k: float = Field(default=0.0, ge=0.0, le=1.0)


class EvalHarnessReport(StrictBaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    arm_id: str
    namespace_id: str
    k: int = Field(..., ge=1)
    query_count: int = Field(..., ge=0)
    url_recall_at_k: float = Field(..., ge=0.0, le=1.0)
    ndcg_at_k: float = Field(..., ge=0.0, le=1.0)
    mrr_at_k: float = Field(..., ge=0.0, le=1.0)
    recall_at_20: float = Field(default=0.0, ge=0.0, le=1.0)
    untitled_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    url_dedup_purity_at_k: float = Field(default=1.0, ge=0.0, le=1.0)
    rare_term_url_recall_at_k: float | None = None
    by_query_type: dict[str, dict[str, float]] = Field(default_factory=dict)
    per_query: list[EvalQueryResult] = Field(default_factory=list)
