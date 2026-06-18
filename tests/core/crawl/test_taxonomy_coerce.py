"""Taxonomy coercion for crawl enrichment."""

import pytest

from core.crawl.models import CrawlPageFilterMetadata
from core.crawl.taxonomy import (
    coerce_filter_metadata_for_taxonomy,
    validate_filter_metadata_against_taxonomy,
)
from core.search.index_models import SearchIndexCrawlTaxonomy

pytestmark = pytest.mark.unit


def _filter_metadata(
    *,
    primary_topic: str = "tech",
    topic_tags: list[str] | None = None,
    category_path: list[str] | None = None,
) -> CrawlPageFilterMetadata:
    return CrawlPageFilterMetadata(
        content_type="article",
        primary_topic=primary_topic,
        topic_tags=topic_tags if topic_tags is not None else ["software", "tech"],
        category_path=category_path if category_path is not None else ["tech"],
        language="ru",
        audience="general",
    )


def _runet_taxonomy() -> SearchIndexCrawlTaxonomy:
    from apps.search.config import SearchCrawlConfig

    config = SearchCrawlConfig.model_validate(
        {"taxonomy_files": {"runet": "conf/crawl_taxonomies/runet.json"}}
    )
    return config.taxonomies["runet"]


def test_coerce_accepts_domain_tag() -> None:
    taxonomy = _runet_taxonomy()
    coerced = coerce_filter_metadata_for_taxonomy(
        _filter_metadata(primary_topic="directory", topic_tags=["domain", "directory"]),
        taxonomy,
    )
    validate_filter_metadata_against_taxonomy(coerced, taxonomy)
    assert "domain" in coerced.topic_tags


def test_coerce_fixes_empty_category_path() -> None:
    taxonomy = _runet_taxonomy()
    coerced = coerce_filter_metadata_for_taxonomy(
        _filter_metadata(primary_topic="other", topic_tags=["other", "reference"], category_path=[]),
        taxonomy,
    )
    validate_filter_metadata_against_taxonomy(coerced, taxonomy)
    assert coerced.category_path == ["other"]


def test_coerce_fixes_lifestyle_hobbies_gardening_path() -> None:
    taxonomy = _runet_taxonomy()
    coerced = coerce_filter_metadata_for_taxonomy(
        _filter_metadata(
            primary_topic="lifestyle",
            topic_tags=["lifestyle", "gardening"],
            category_path=["lifestyle", "hobbies", "gardening"],
        ),
        taxonomy,
    )
    validate_filter_metadata_against_taxonomy(coerced, taxonomy)
    assert coerced.category_path == ["lifestyle", "hobbies", "gardening"]


def test_coerce_strips_schema_field_names_from_topic_tags() -> None:
    taxonomy = _runet_taxonomy()
    coerced = coerce_filter_metadata_for_taxonomy(
        _filter_metadata(
            primary_topic="tech",
            topic_tags=["category_path", "software"],
            category_path=["tech"],
        ),
        taxonomy,
    )
    validate_filter_metadata_against_taxonomy(coerced, taxonomy)
    assert "category_path" not in coerced.topic_tags


def test_coerce_accepts_bare_metal_tag() -> None:
    taxonomy = _runet_taxonomy()
    coerced = coerce_filter_metadata_for_taxonomy(
        _filter_metadata(
            primary_topic="hardware",
            topic_tags=["bare_metal", "hardware"],
            category_path=["tech", "hardware"],
        ),
        taxonomy,
    )
    validate_filter_metadata_against_taxonomy(coerced, taxonomy)
    assert "bare_metal" in coerced.topic_tags


def test_coerce_accepts_data_science_infrastructure_browser() -> None:
    taxonomy = _runet_taxonomy()
    coerced = coerce_filter_metadata_for_taxonomy(
        _filter_metadata(
            primary_topic="data_science",
            topic_tags=["data_science", "machine_learning"],
            category_path=["tech", "ai", "data_science"],
        ),
        taxonomy,
    )
    validate_filter_metadata_against_taxonomy(coerced, taxonomy)
    coerced_infra = coerce_filter_metadata_for_taxonomy(
        _filter_metadata(
            primary_topic="infrastructure",
            topic_tags=["infrastructure", "cloud"],
            category_path=["tech", "cloud", "infrastructure"],
        ),
        taxonomy,
    )
    validate_filter_metadata_against_taxonomy(coerced_infra, taxonomy)
    coerced_browser = coerce_filter_metadata_for_taxonomy(
        _filter_metadata(
            primary_topic="browser",
            topic_tags=["browser", "software"],
            category_path=["tech", "software", "browser"],
        ),
        taxonomy,
    )
    validate_filter_metadata_against_taxonomy(coerced_browser, taxonomy)
