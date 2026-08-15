"""
Метаданные страниц в RAG и сборка фильтров.

Метаданные — рабочий инструмент точного поиска, поэтому проверяется и полнота
набора, и то, что каждое условие превращается в фильтр, который понимает
pgvector: только скаляры и только поддерживаемые операторы.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from apps.wiki.content.prosemirror import empty_document
from apps.wiki.models.domain import WikiPage
from apps.wiki.services.rag_metadata import (
    MAX_PAGE_ID_FILTER_SIZE,
    WIKI_SOURCE_KIND,
    WikiRagFilterOverflowError,
    WikiSearchFilter,
    build_wiki_chunk_metadata,
    build_wiki_search_filter,
)

NOW = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)


def make_page(**overrides: object) -> WikiPage:
    payload: dict[str, object] = {
        "wiki_page_id": "wpg_child",
        "company_id": "c1",
        "namespace": "sales",
        "parent_page_id": "wpg_root",
        "root_page_id": "wpg_root",
        "depth": 2,
        "title": "Регламент",
        "content": empty_document(),
        "text_markdown": "Регламент отдела",
        "created_by_user_id": "u_author",
        "last_edited_by_user_id": "u_editor",
        "created_at": NOW,
        "updated_at": NOW,
    }
    payload.update(overrides)
    return WikiPage.model_validate(payload)


def test_chunk_metadata_contains_full_field_set():
    metadata = build_wiki_chunk_metadata(make_page(), heading_path="Регламент / Отпуска")
    assert metadata == {
        "document_id": "wpg_child",
        "company_id": "c1",
        "source_kind": WIKI_SOURCE_KIND,
        "ttl_seconds": 0,
        "wiki_namespace": "sales",
        "wiki_page_id": "wpg_child",
        "wiki_parent_page_id": "wpg_root",
        "wiki_root_page_id": "wpg_root",
        "wiki_depth": 2,
        "wiki_visibility": "company",
        "wiki_is_published": True,
        "wiki_title": "Регламент",
        "wiki_heading_path": "Регламент / Отпуска",
        "wiki_updated_at_ts": int(NOW.timestamp()),
        "wiki_author_user_id": "u_author",
        "wiki_last_editor_user_id": "u_editor",
    }


def test_chunk_metadata_values_are_scalars():
    # pgvector сравнивает только string/number/boolean; список сломал бы фильтр.
    metadata = build_wiki_chunk_metadata(make_page())
    for key, value in metadata.items():
        assert isinstance(value, (str, int, float, bool)), key


def test_root_page_without_parent_has_empty_parent_field():
    page = make_page(wiki_page_id="wpg_root", parent_page_id=None, depth=0)
    metadata = build_wiki_chunk_metadata(page)
    assert metadata["wiki_parent_page_id"] == ""
    assert metadata["wiki_depth"] == 0


def test_restricted_page_marks_visibility():
    page = make_page(company_visible=False)
    assert build_wiki_chunk_metadata(page)["wiki_visibility"] == "restricted"


def test_filter_always_scopes_to_wiki_and_namespace():
    filters = build_wiki_search_filter(WikiSearchFilter(namespace="sales"))
    assert filters == {
        "$and": [
            {"source_kind": {"$eq": WIKI_SOURCE_KIND}},
            {"wiki_namespace": {"$eq": "sales"}},
        ]
    }


def test_section_scope_uses_scalar_root_filter():
    # Самый частый структурный запрос не должен разворачиваться в список id.
    filters = build_wiki_search_filter(
        WikiSearchFilter(namespace="sales", root_page_id="wpg_root")
    )
    assert {"wiki_root_page_id": {"$eq": "wpg_root"}} in filters["$and"]


def test_published_and_freshness_conditions():
    updated_after = NOW - timedelta(days=7)
    filters = build_wiki_search_filter(
        WikiSearchFilter(namespace="sales", published_only=True, updated_after=updated_after)
    )
    conditions = filters["$and"]
    assert {"wiki_is_published": {"$eq": True}} in conditions
    assert {"wiki_updated_at_ts": {"$gte": int(updated_after.timestamp())}} in conditions


def test_editor_and_depth_conditions():
    filters = build_wiki_search_filter(
        WikiSearchFilter(namespace="sales", editor_user_id="u_editor", max_depth=1)
    )
    conditions = filters["$and"]
    assert {"wiki_last_editor_user_id": {"$eq": "u_editor"}} in conditions
    assert {"wiki_depth": {"$lte": 1}} in conditions


def test_allowed_page_ids_become_in_filter():
    filters = build_wiki_search_filter(
        WikiSearchFilter(namespace="sales", allowed_page_ids=["wpg_a", "wpg_b"])
    )
    assert {"wiki_page_id": {"$in": ["wpg_a", "wpg_b"]}} in filters["$and"]


def test_oversized_page_list_is_rejected_instead_of_truncated():
    too_many = [f"wpg_{index}" for index in range(MAX_PAGE_ID_FILTER_SIZE + 1)]
    with pytest.raises(WikiRagFilterOverflowError):
        _ = build_wiki_search_filter(
            WikiSearchFilter(namespace="sales", allowed_page_ids=too_many)
        )
