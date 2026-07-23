"""Тесты единого резолвера platform search_defaults."""

from __future__ import annotations

from core.config.base import get_settings
from core.config.models import RAGConfig
from core.rag.models import RAGSearchOptions
from core.rag.search_options_resolver import resolve_platform_search_options
from core.rag_indexing_schema import (
    IndexProfileConfig,
    IndexProfileSearchDefaults,
    RerankerSearchDefaults,
    SearchChannelsDefaults,
)


class _SettingsStub:
    def __init__(self, rag: RAGConfig) -> None:
        self.rag: RAGConfig = rag


def _settings_with_search_defaults(
    search_defaults: IndexProfileSearchDefaults | None,
) -> _SettingsStub:
    return _SettingsStub(
        rag=RAGConfig(
            enabled=True,
            default_provider="pgvector",
            document_indexing=IndexProfileConfig(search_defaults=search_defaults),
        )
    )


def test_resolver_falls_back_to_hybrid_channels_when_defaults_absent() -> None:
    resolved = resolve_platform_search_options(
        settings=_settings_with_search_defaults(None),
    )
    assert resolved.channels is not None
    assert resolved.channels.semantic is True
    assert resolved.channels.lexical is True


def test_resolver_reads_document_indexing_search_defaults() -> None:
    resolved = resolve_platform_search_options(
        settings=_settings_with_search_defaults(
            IndexProfileSearchDefaults(
                channels=SearchChannelsDefaults(semantic=True, lexical=True),
                rrf_k=42,
                per_channel_top_k=99,
                reranker=RerankerSearchDefaults(enabled=True, max_candidates=17),
            )
        ),
    )
    assert resolved.rrf_k == 42
    assert resolved.per_channel_top_k == 99
    assert resolved.rerank is True
    assert resolved.rerank_max_candidates == 17


def test_resolver_call_override_wins_over_platform_defaults() -> None:
    resolved = resolve_platform_search_options(
        settings=_settings_with_search_defaults(
            IndexProfileSearchDefaults(
                channels=SearchChannelsDefaults(semantic=True, lexical=True),
                rrf_k=60,
            )
        ),
        overrides=RAGSearchOptions(
            channels=SearchChannelsDefaults(semantic=True, lexical=False),
            rrf_k=11,
        ),
    )
    assert resolved.channels is not None
    assert resolved.channels.lexical is False
    assert resolved.rrf_k == 11


def test_resolver_per_channel_top_k_argument_overrides_profile_default() -> None:
    resolved = resolve_platform_search_options(
        settings=_settings_with_search_defaults(
            IndexProfileSearchDefaults(per_channel_top_k=120)
        ),
        per_channel_top_k=55,
    )
    assert resolved.per_channel_top_k == 55


def test_resolver_uses_live_conf_search_defaults() -> None:
    """Регрессия: conf.json seed с search_defaults не ломает резолвер."""
    settings = get_settings()
    resolved = resolve_platform_search_options(settings=settings)
    assert resolved.channels is not None
    assert resolved.channels.semantic is True
    assert resolved.channels.lexical is True
