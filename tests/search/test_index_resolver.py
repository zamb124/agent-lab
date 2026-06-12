"""Index resolver unit tests."""

import pytest

from apps.search.config import SearchIndexProviderConfig
from apps.search.services.index_resolver import preprocess_meta_search_request
from core.search.models import MetaSearchRequest


def test_index_colon_runet_gov_ru() -> None:
    prepared = preprocess_meta_search_request(
        MetaSearchRequest(
            query="test",
            providers=["index:runet,gov_ru"],
        ),
        SearchIndexProviderConfig(),
    )
    assert prepared.index_ids == ["runet", "gov_ru"]
    assert prepared.request.providers == ["index"]


def test_runet_alias_maps_to_index() -> None:
    prepared = preprocess_meta_search_request(
        MetaSearchRequest(query="test", providers=["runet"]),
        SearchIndexProviderConfig(),
    )
    assert prepared.index_ids == ["runet"]
    assert prepared.request.providers == ["index"]


def test_auto_uses_default_index_ids() -> None:
    prepared = preprocess_meta_search_request(
        MetaSearchRequest(query="test", providers=["auto"]),
        SearchIndexProviderConfig(default_index_ids=["runet"]),
    )
    assert prepared.index_ids == ["runet"]
    assert prepared.request.providers == ["auto"]
    assert prepared.request.index_ids == ["runet"]


def test_index_without_ids_uses_defaults() -> None:
    prepared = preprocess_meta_search_request(
        MetaSearchRequest(query="test", providers=["index"]),
        SearchIndexProviderConfig(default_index_ids=["runet"]),
    )
    assert prepared.index_ids == ["runet"]


def test_index_without_ids_and_defaults_raises() -> None:
    with pytest.raises(ValueError, match="index_ids are required"):
        preprocess_meta_search_request(
            MetaSearchRequest(query="test", providers=["index"]),
            SearchIndexProviderConfig(default_index_ids=[]),
        )
