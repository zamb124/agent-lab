"""Runet crawl taxonomy completeness."""

from typing import get_args

import pytest

from apps.search.config import SearchCrawlConfig
from core.crawl.models import CrawlPageContentType

pytestmark = pytest.mark.unit


def test_runet_taxonomy_file_is_comprehensive() -> None:
    config = SearchCrawlConfig.model_validate(
        {"taxonomy_files": {"runet": "conf/crawl_taxonomies/runet.json"}}
    )
    taxonomy = config.taxonomies["runet"]

    assert len(taxonomy.primary_topics) >= 100
    assert len(taxonomy.topic_tags) >= 250
    assert len(taxonomy.category_paths) >= 200
    for primary_topic in taxonomy.primary_topics:
        assert primary_topic in taxonomy.topic_tags


def test_crawl_page_content_type_includes_rich_page_kinds() -> None:
    content_types = set(get_args(CrawlPageContentType))
    expected = {
        "blog",
        "tutorial",
        "guide",
        "review",
        "press_release",
        "research",
        "case_study",
        "changelog",
        "wiki",
        "tool",
        "recipe",
        "report",
        "transcript",
        "directory",
        "portfolio",
    }
    assert expected.issubset(content_types)
