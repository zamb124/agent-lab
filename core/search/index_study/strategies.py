"""Pluggable index_study_strategy arms (§4.11)."""

from __future__ import annotations

from typing import ClassVar

from pydantic import ConfigDict, Field

from core.models import StrictBaseModel
from core.search.pointer_models import INDEX_STUDY_STRATEGIES, IndexStudyStrategy


class IndexStudyStrategySpec(StrictBaseModel):
    """Описание одной study strategy для eval и crawl ingest."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    strategy_id: IndexStudyStrategy
    display_name: str
    description: str
    vectors_per_url_typical: str
    lexical_strength: str
    llm_required: bool = False


class IndexStudyArmDefinition(StrictBaseModel):
    """Shadow eval arm: namespace + strategy binding."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    arm_id: str = Field(..., min_length=1, max_length=64)
    strategy: IndexStudyStrategy
    shadow_namespace_suffix: str = Field(..., min_length=1, max_length=128)
    notes: str = ""


_INDEX_STUDY_SPECS: dict[IndexStudyStrategy, IndexStudyStrategySpec] = {
    "lexical": IndexStudyStrategySpec(
        strategy_id="lexical",
        display_name="Lexical salient terms",
        description="salient_terms extractor → 1× dense embed(term bag) + metadata.terms[]",
        vectors_per_url_typical="1",
        lexical_strength="★★★★",
        llm_required=False,
    ),
    "split_embed": IndexStudyStrategySpec(
        strategy_id="split_embed",
        display_name="Heading split embed",
        description="heading-split → N× section embed; section text discard after embed",
        vectors_per_url_typical="3–12",
        lexical_strength="★★",
        llm_required=False,
    ),
    "llm_embed": IndexStudyStrategySpec(
        strategy_id="llm_embed",
        display_name="LLM summary embed",
        description="LLM page/section summaries → K× embed; LLM text discard",
        vectors_per_url_typical="1–6",
        lexical_strength="★★★",
        llm_required=True,
    ),
    "hybrid_study": IndexStudyStrategySpec(
        strategy_id="hybrid_study",
        display_name="Lexical + split embed",
        description="salient_terms + section vectors (N+1)",
        vectors_per_url_typical="4–13",
        lexical_strength="★★★★",
        llm_required=False,
    ),
}

_INDEX_STUDY_ARMS: tuple[IndexStudyArmDefinition, ...] = tuple(
    IndexStudyArmDefinition(
        arm_id=strategy_id,
        strategy=strategy_id,
        shadow_namespace_suffix=f"runet:eval:study:{strategy_id}",
        notes=_INDEX_STUDY_SPECS[strategy_id].description,
    )
    for strategy_id in INDEX_STUDY_STRATEGIES
)


def list_index_study_specs() -> list[IndexStudyStrategySpec]:
    return [_INDEX_STUDY_SPECS[s] for s in INDEX_STUDY_STRATEGIES]


def get_index_study_spec(strategy: IndexStudyStrategy) -> IndexStudyStrategySpec:
    return _INDEX_STUDY_SPECS[strategy]


def list_index_study_arms() -> list[IndexStudyArmDefinition]:
    return list(_INDEX_STUDY_ARMS)
