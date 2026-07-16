"""Shadow A/B chunking arms для eval slice (§13.4)."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import ConfigDict

from core.models import StrictBaseModel
from core.rag_indexing_schema import IndexProfileSplitConfig

ChunkingArmId = Literal[
    "as_is",
    "fixed_512",
    "structure_800",
    "recursive_512",
    "semantic_800",
    "llm_page_meta_only",
]

CHUNKING_ARM_IDS: tuple[ChunkingArmId, ...] = (
    "as_is",
    "fixed_512",
    "structure_800",
    "recursive_512",
    "semantic_800",
    "llm_page_meta_only",
)


class ChunkingArmDefinition(StrictBaseModel):
    """Один shadow arm full-chunk baseline eval (Phase 0b)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    arm_id: ChunkingArmId
    display_name: str
    shadow_namespace_suffix: str
    split: IndexProfileSplitConfig | None = None
    use_pgvector_default_chunk: bool = False
    lexical_enabled: bool = True
    llm_page_enrichment: bool = False
    llm_summary_metadata_only: bool = False
    purpose: str


def chunking_arm_namespace(arm_id: ChunkingArmId, *, base: str = "runet") -> str:
    return f"{base}:eval:chunk:{arm_id}"


_CHUNKING_ARMS: dict[ChunkingArmId, ChunkingArmDefinition] = {
    "as_is": ChunkingArmDefinition(
        arm_id="as_is",
        display_name="As-is crawl (pgvector 1000/100)",
        shadow_namespace_suffix=chunking_arm_namespace("as_is"),
        use_pgvector_default_chunk=True,
        lexical_enabled=True,
        llm_page_enrichment=True,
        purpose="Production baseline до page-card",
    ),
    "fixed_512": ChunkingArmDefinition(
        arm_id="fixed_512",
        display_name="Fixed tokens 512/50",
        shadow_namespace_suffix=chunking_arm_namespace("fixed_512"),
        split=IndexProfileSplitConfig(strategy="fixed_tokens", chunk_size=512, chunk_overlap=50),
        purpose="NAACL 2025 control arm",
    ),
    "structure_800": ChunkingArmDefinition(
        arm_id="structure_800",
        display_name="Structure headings 800/120",
        shadow_namespace_suffix=chunking_arm_namespace("structure_800"),
        split=IndexProfileSplitConfig(strategy="structure", chunk_size=800, chunk_overlap=120),
        purpose="Primary challenger для web markdown",
    ),
    "recursive_512": ChunkingArmDefinition(
        arm_id="recursive_512",
        display_name="Recursive 512/50",
        shadow_namespace_suffix=chunking_arm_namespace("recursive_512"),
        split=IndexProfileSplitConfig(strategy="recursive", chunk_size=512, chunk_overlap=50),
        purpose="Universal recursive control arm",
    ),
    "semantic_800": ChunkingArmDefinition(
        arm_id="semantic_800",
        display_name="Semantic 800/120 (conf runet_web)",
        shadow_namespace_suffix=chunking_arm_namespace("semantic_800"),
        split=IndexProfileSplitConfig(strategy="semantic", chunk_size=800, chunk_overlap=120),
        purpose="Текущая гипотеза conf runet_web",
    ),
    "llm_page_meta_only": ChunkingArmDefinition(
        arm_id="llm_page_meta_only",
        display_name="Structure + LLM metadata only",
        shadow_namespace_suffix=chunking_arm_namespace("llm_page_meta_only"),
        split=IndexProfileSplitConfig(strategy="structure", chunk_size=800, chunk_overlap=120),
        llm_page_enrichment=True,
        llm_summary_metadata_only=True,
        purpose="Разделение display title vs index text",
    ),
}


def get_chunking_arm(arm_id: ChunkingArmId) -> ChunkingArmDefinition:
    return _CHUNKING_ARMS[arm_id]


def list_chunking_arms() -> list[ChunkingArmDefinition]:
    return [_CHUNKING_ARMS[arm_id] for arm_id in CHUNKING_ARM_IDS]
