"""Слияние частичного index_profile_config с базовым профилем."""

from core.config import get_settings
from core.rag.index_profile_merge import (
    deep_merge_dict,
    merge_index_profile_config,
    merge_index_profile_dict_overlays,
)
from core.rag_indexing_schema import IndexProfileConfig


def test_deep_merge_dict_nested() -> None:
    base = {"split": {"strategy": "fixed_tokens", "chunk_size": 512}, "parsing": {"engine": "unstructured"}}
    override = {"split": {"strategy": "semantic"}}
    assert deep_merge_dict(base, override) == {
        "split": {"strategy": "semantic", "chunk_size": 512},
        "parsing": {"engine": "unstructured"},
    }


def test_merge_index_profile_config_preserves_chunk_size() -> None:
    base = get_settings().rag.document_indexing
    merged = merge_index_profile_config(base, {"split": {"strategy": "semantic"}})
    assert merged.split.strategy == "semantic"
    assert merged.split.chunk_size == base.split.chunk_size


def test_merge_index_profile_dict_overlays_order() -> None:
    a = {"split": {"strategy": "fixed_tokens", "chunk_size": 100}}
    b = {"split": {"strategy": "semantic"}}
    c = merge_index_profile_dict_overlays(a, b)
    assert c == {"split": {"strategy": "semantic", "chunk_size": 100}}
    out = IndexProfileConfig.model_validate(c)
    assert out.split.strategy == "semantic"
    assert out.split.chunk_size == 100
