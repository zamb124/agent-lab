"""Tests for IndexStudyService / apply_index_study (§4.11)."""

from __future__ import annotations

import pytest

from core.crawl.models import CrawlEnrichedChunk, CrawlEnrichedPage
from core.search.index_study.service import apply_index_study

_HABR_MARKDOWN = """# Kubernetes Ingress: полное руководство

Эта статья про настройку ingress-nginx на Kubernetes 1.29.

## Установка

Используйте helm для установки ingress-nginx v1.9.4.

## Настройка TLS

Настройте cert-manager для автоматического получения TLS-сертификатов.

### Let's Encrypt

Используйте ClusterIssuer для Let's Encrypt.

## Устранение неисправностей

Проверьте логи пода ingress-controller.
"""


def test_lexical_strategy_returns_one_global_vector() -> None:
    specs = apply_index_study(
        _HABR_MARKDOWN,
        "Kubernetes Ingress: полное руководство",
        strategy="lexical",
    )
    assert len(specs) == 1
    assert specs[0].vector_role == "global"
    assert specs[0].vector_index == 0


def test_lexical_strategy_embed_text_contains_title_and_terms() -> None:
    specs = apply_index_study(
        _HABR_MARKDOWN,
        "Kubernetes Ingress Guide",
        strategy="lexical",
        salient_terms_max=80,
    )
    embed_text = specs[0].embed_text
    assert "Kubernetes" in embed_text
    assert len(specs[0].salient_terms) > 0


def test_lexical_strategy_sections_in_metadata() -> None:
    specs = apply_index_study(
        _HABR_MARKDOWN,
        "Guide",
        strategy="lexical",
    )
    assert "Установка" in specs[0].section_titles or any(
        "Настройка" in t for t in specs[0].section_titles
    )


def test_split_embed_returns_global_plus_sections() -> None:
    specs = apply_index_study(
        _HABR_MARKDOWN,
        "Guide",
        strategy="split_embed",
        max_vectors=12,
    )
    roles = [s.vector_role for s in specs]
    assert "global" in roles
    assert "section" in roles
    assert len(specs) > 1


def test_split_embed_respects_max_vectors() -> None:
    specs = apply_index_study(
        _HABR_MARKDOWN,
        "Guide",
        strategy="split_embed",
        max_vectors=3,
    )
    assert len(specs) <= 3


def test_split_embed_section_has_heading_trail() -> None:
    specs = apply_index_study(
        _HABR_MARKDOWN,
        "Guide",
        strategy="split_embed",
        max_vectors=12,
    )
    section_specs = [s for s in specs if s.vector_role == "section"]
    assert len(section_specs) > 0
    # At least one section should have a non-empty heading trail or section_title
    has_meta = any(s.heading_trail or s.section_title for s in section_specs)
    assert has_meta


def test_hybrid_study_includes_salient_vector() -> None:
    specs = apply_index_study(
        _HABR_MARKDOWN,
        "Guide",
        strategy="hybrid_study",
        max_vectors=12,
    )
    roles = [s.vector_role for s in specs]
    assert "global" in roles
    assert "section" in roles
    assert "salient" in roles


def test_hybrid_study_salient_embed_text_is_terms() -> None:
    specs = apply_index_study(
        _HABR_MARKDOWN,
        "Guide",
        strategy="hybrid_study",
        max_vectors=12,
        salient_terms_max=20,
    )
    salient = next(s for s in specs if s.vector_role == "salient")
    # Embed text should be non-empty and come from salient_terms
    assert salient.embed_text.strip()
    assert len(salient.salient_terms) > 0


def _sample_enriched_page() -> CrawlEnrichedPage:
    return CrawlEnrichedPage(
        page_summary="Kubernetes Ingress: полное руководство",
        chunks=[
            CrawlEnrichedChunk(
                content="helm install ingress-nginx...",
                metadata_summary="Установка ingress-nginx через helm",
                hierarchy=["Установка"],
            ),
            CrawlEnrichedChunk(
                content="cert-manager ClusterIssuer...",
                metadata_summary="Настройка TLS через cert-manager",
                hierarchy=["Настройка TLS", "Let's Encrypt"],
            ),
        ],
        enrichment_model="qwen/qwen2.5-1.5b-instruct-crawl",
        enrichment_prompt_version="v1",
    )


def test_llm_embed_requires_enriched_page() -> None:
    with pytest.raises(ValueError, match="enriched_page"):
        apply_index_study(_HABR_MARKDOWN, "Guide", strategy="llm_embed")


def test_llm_embed_builds_global_and_section_vectors() -> None:
    enriched = _sample_enriched_page()
    specs = apply_index_study(
        _HABR_MARKDOWN,
        "Guide",
        strategy="llm_embed",
        enriched_page=enriched,
        max_vectors=12,
    )
    roles = [s.vector_role for s in specs]
    assert roles[0] == "global"
    assert "section" in roles
    assert specs[0].embed_text == enriched.page_summary
    assert any("cert-manager" in s.embed_text for s in specs if s.vector_role == "section")


def test_llm_embed_respects_max_vectors() -> None:
    enriched = _sample_enriched_page()
    specs = apply_index_study(
        _HABR_MARKDOWN,
        "Guide",
        strategy="llm_embed",
        enriched_page=enriched,
        max_vectors=2,
    )
    assert len(specs) == 2


def test_unknown_strategy_raises_error() -> None:
    with pytest.raises((ValueError, AssertionError)):
        apply_index_study(_HABR_MARKDOWN, "Guide", strategy="nonexistent")  # type: ignore[arg-type]


def test_vector_index_is_sequential() -> None:
    specs = apply_index_study(
        _HABR_MARKDOWN,
        "Guide",
        strategy="split_embed",
        max_vectors=12,
    )
    indices = [s.vector_index for s in specs]
    assert indices == list(range(len(specs)))


def test_short_page_returns_at_least_one_spec() -> None:
    md = "# Title\n\nShort content.\n"
    for strategy in ("lexical", "split_embed", "hybrid_study"):
        specs = apply_index_study(md, "Title", strategy=strategy)  # type: ignore[arg-type]
        assert len(specs) >= 1, f"strategy={strategy} returned empty specs"
