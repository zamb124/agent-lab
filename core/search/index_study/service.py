"""IndexStudyService: build index-vector specs from markdown without persisting prose (§4.11).

Each strategy produces a list of IndexVectorSpec — one per planned DB row.
The embed_text field is fed to the embedding model; prose is discarded after
embed.  The DB row stores metadata + embedding only (content = stub or debug text).

Strategies:
  lexical     — 1× global vector (title + section_titles + salient_terms)
  split_embed — global + N× section vectors; section text capped per spec
  hybrid_study— split_embed + 1× salient vector (bag-of-terms)
  llm_embed   — K× embed from CrawlEnrichedPage (LLM output discarded after embed)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import assert_never

from core.crawl.models import CrawlEnrichedChunk, CrawlEnrichedPage
from core.search.markdown_headings import ParsedSection, parse_sections
from core.search.pointer_models import IndexStudyStrategy, VectorRole
from core.search.salient_terms import extract_salient_terms


@dataclass
class IndexVectorSpec:
    """Spec for one index-vector row (no prose in DB)."""

    embed_text: str
    vector_role: VectorRole
    vector_index: int
    section_title: str | None = None
    heading_trail: list[str] = field(default_factory=list)
    salient_terms: list[str] = field(default_factory=list)
    section_titles: list[str] = field(default_factory=list)


def apply_index_study(
    markdown: str,
    title: str,
    *,
    strategy: IndexStudyStrategy,
    enriched_page: CrawlEnrichedPage | None = None,
    salient_terms: list[str] | None = None,
    max_vectors: int = 12,
    salient_terms_max: int = 80,
    max_section_tokens: int = 200,
) -> list[IndexVectorSpec]:
    """Build index vector specs from page markdown.

    Texts are for embedding only; caller must not persist them as prose.
    llm_embed requires enriched_page from CrawlPageEnrichmentService (orchestrator).
    """
    if strategy == "lexical":
        return _apply_lexical(
            markdown,
            title,
            salient_terms=salient_terms,
            salient_terms_max=salient_terms_max,
        )
    if strategy == "split_embed":
        return _apply_split_embed(
            markdown,
            title,
            salient_terms=salient_terms,
            max_vectors=max_vectors,
            max_section_tokens=max_section_tokens,
            salient_terms_max=salient_terms_max,
        )
    if strategy == "hybrid_study":
        return _apply_hybrid_study(
            markdown,
            title,
            salient_terms=salient_terms,
            max_vectors=max_vectors,
            max_section_tokens=max_section_tokens,
            salient_terms_max=salient_terms_max,
        )
    if strategy == "llm_embed":
        if enriched_page is None:
            raise ValueError(
                "llm_embed requires enriched_page; enable crawl profile llm_enrichment_enabled"
            )
        return _apply_llm_embed(
            enriched_page,
            title,
            max_vectors=max_vectors,
            max_section_tokens=max_section_tokens,
        )
    assert_never(strategy)


def _build_global_embed_text(
    title: str,
    section_titles: list[str],
    salient_terms: list[str],
) -> str:
    parts: list[str] = []
    if title:
        parts.append(title)
    if section_titles:
        parts.append(" · ".join(section_titles[:8]))
    if salient_terms:
        parts.append(" ".join(salient_terms[:40]))
    return " ".join(parts)


def _section_titles_from(sections: list[ParsedSection]) -> list[str]:
    return [s.section_title for s in sections if s.section_title]


def _resolve_salient_terms(
    markdown: str,
    *,
    salient_terms: list[str] | None,
    salient_terms_max: int,
) -> list[str]:
    if salient_terms is not None:
        return salient_terms
    return extract_salient_terms(markdown, max_terms=salient_terms_max)


def _apply_lexical(
    markdown: str,
    title: str,
    *,
    salient_terms: list[str] | None,
    salient_terms_max: int,
) -> list[IndexVectorSpec]:
    terms = _resolve_salient_terms(
        markdown,
        salient_terms=salient_terms,
        salient_terms_max=salient_terms_max,
    )
    sections = parse_sections(markdown, max_section_tokens=0)
    section_titles = _section_titles_from(sections)
    embed_text = _build_global_embed_text(title, section_titles, terms)
    return [
        IndexVectorSpec(
            embed_text=embed_text,
            vector_role="global",
            vector_index=0,
            salient_terms=terms,
            section_titles=section_titles,
        )
    ]


def _apply_split_embed(
    markdown: str,
    title: str,
    *,
    salient_terms: list[str] | None,
    max_vectors: int,
    max_section_tokens: int,
    salient_terms_max: int,
) -> list[IndexVectorSpec]:
    sections = parse_sections(markdown, max_section_tokens=max_section_tokens)
    terms = _resolve_salient_terms(
        markdown,
        salient_terms=salient_terms,
        salient_terms_max=salient_terms_max,
    )
    section_titles = _section_titles_from(sections)

    specs: list[IndexVectorSpec] = []

    # Global vector (index 0)
    global_embed = _build_global_embed_text(title, section_titles, terms)
    specs.append(
        IndexVectorSpec(
            embed_text=global_embed,
            vector_role="global",
            vector_index=0,
            salient_terms=terms,
            section_titles=section_titles,
        )
    )

    # Section vectors (cap: max_vectors - 1 to reserve global slot)
    section_cap = max(1, max_vectors - 1)
    for i, section in enumerate(sections[:section_cap]):
        if not section.section_title and not section.text:
            continue
        trail_prefix = " > ".join(section.heading_trail) if section.heading_trail else ""
        if trail_prefix:
            section_embed = f"{trail_prefix}: {section.text}"
        else:
            section_embed = section.text
        specs.append(
            IndexVectorSpec(
                embed_text=section_embed.strip(),
                vector_role="section",
                vector_index=i + 1,
                section_title=section.section_title or None,
                heading_trail=list(section.heading_trail),
            )
        )

    return specs


def _apply_hybrid_study(
    markdown: str,
    title: str,
    *,
    salient_terms: list[str] | None,
    max_vectors: int,
    max_section_tokens: int,
    salient_terms_max: int,
) -> list[IndexVectorSpec]:
    # Reserve one slot for the salient vector
    split_specs = _apply_split_embed(
        markdown,
        title,
        salient_terms=salient_terms,
        max_vectors=max(2, max_vectors - 1),
        max_section_tokens=max_section_tokens,
        salient_terms_max=salient_terms_max,
    )

    terms = _resolve_salient_terms(
        markdown,
        salient_terms=salient_terms,
        salient_terms_max=salient_terms_max,
    )
    salient_embed = " ".join(terms)
    if salient_embed.strip():
        salient_spec = IndexVectorSpec(
            embed_text=salient_embed,
            vector_role="salient",
            vector_index=len(split_specs),
            salient_terms=terms,
        )
        return [*split_specs, salient_spec]

    return split_specs


def _llm_chunk_embed_text(chunk: CrawlEnrichedChunk, *, max_section_tokens: int) -> str:
    heading = " > ".join(part.strip() for part in chunk.hierarchy if part.strip())
    summary = chunk.metadata_summary.strip()
    if heading and summary:
        return f"{heading}: {summary}"
    if summary:
        return summary
    if heading:
        return heading
    words = chunk.content.split()
    return " ".join(words[:max_section_tokens])


def _section_titles_from_enriched_chunks(chunks: list[CrawlEnrichedChunk]) -> list[str]:
    titles: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        if chunk.hierarchy:
            title = chunk.hierarchy[-1].strip()
        else:
            title = chunk.metadata_summary.strip()[:80]
        if title and title.lower() not in seen:
            seen.add(title.lower())
            titles.append(title)
    return titles


def _apply_llm_embed(
    enriched_page: CrawlEnrichedPage,
    title: str,
    *,
    max_vectors: int,
    max_section_tokens: int,
) -> list[IndexVectorSpec]:
    """Build index vectors from LLM enrichment output; prose discarded after embed."""
    section_titles = _section_titles_from_enriched_chunks(enriched_page.chunks)
    global_embed = enriched_page.page_summary.strip() or title
    specs: list[IndexVectorSpec] = [
        IndexVectorSpec(
            embed_text=global_embed,
            vector_role="global",
            vector_index=0,
            section_titles=section_titles,
        )
    ]
    section_cap = max(1, max_vectors - 1)
    section_index = 1
    for chunk in enriched_page.chunks[:section_cap]:
        embed_text = _llm_chunk_embed_text(chunk, max_section_tokens=max_section_tokens)
        if not embed_text.strip():
            continue
        heading_trail = [part.strip() for part in chunk.hierarchy if part.strip()]
        section_title = heading_trail[-1] if heading_trail else chunk.metadata_summary.strip()[:80] or None
        specs.append(
            IndexVectorSpec(
                embed_text=embed_text,
                vector_role="section",
                vector_index=section_index,
                section_title=section_title,
                heading_trail=heading_trail,
            )
        )
        section_index += 1
    return specs[:max_vectors]
