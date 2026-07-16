"""Tests for runet pointer config and crawl ingest metadata."""

from __future__ import annotations

from apps.search.config import SearchSettings, get_search_settings, reset_search_settings
from core.search.pointer_models import POINTER_INDEX_CONTENT_STUB, resolve_index_content_stub


def test_runet_pointer_config_defaults() -> None:
    settings = SearchSettings.model_validate(
        {
            "database": {"search_url": "postgresql://localhost/search"},
            "runet": {
                "index_mode": "vector_pointer",
                "index_study_strategy": "lexical",
                "index_study_strategies_eval": ["lexical", "split_embed", "hybrid_study"],
            },
        },
    )
    assert settings.runet.index_mode == "vector_pointer"
    assert settings.runet.index_study_strategy == "lexical"
    assert settings.runet.research.fetch_concurrency == 5
    assert settings.runet.research.browser_pool_size == 3


def test_resolve_index_content_stub() -> None:
    assert resolve_index_content_stub(persist_debug=False, debug_preview="preview") == POINTER_INDEX_CONTENT_STUB
    assert (
        resolve_index_content_stub(persist_debug=True, debug_preview="  debug text  ")
        == "debug text"
    )


def test_search_settings_loads_runet_from_merged_config() -> None:
    reset_search_settings()
    settings = get_search_settings()
    assert settings.runet.index_mode == "vector_pointer"
    assert settings.runet.index_study_strategies_eval == ["lexical", "split_embed", "hybrid_study"]
    reset_search_settings()
