"""Seed-пары embedding/rerank: без дублей по api и каноничному HF."""

from apps.provider_litserve.catalog import (
    build_embedding_seed_entries,
    build_rerank_seed_entries,
)
from core.config.models import ProviderLitserveInfraConfig


def _pairs(entries) -> dict[str, str]:
    return {e.api_model_id: e.hf_model_id for e in entries}


def test_embedding_pairs_no_duplicate_hf_row_when_openai_alias_present() -> None:
    cfg = ProviderLitserveInfraConfig(
        embedding_model_id="BAAI/bge-m3",
        embedding_openai_model_id="baai/bge-m3",
        embedding_model_ids=[],
    )
    assert _pairs(build_embedding_seed_entries(cfg)) == {"baai/bge-m3": "BAAI/bge-m3"}


def test_embedding_pairs_skips_case_duplicate_list_keys() -> None:
    cfg = ProviderLitserveInfraConfig(
        embedding_model_id="BAAI/bge-m3",
        embedding_openai_model_id="baai/bge-m3",
        embedding_model_ids=["BAAI/bge-m3"],
    )
    assert _pairs(build_embedding_seed_entries(cfg)) == {"baai/bge-m3": "BAAI/bge-m3"}


def test_embedding_pairs_extra_model_in_list() -> None:
    cfg = ProviderLitserveInfraConfig(
        embedding_model_id="BAAI/bge-m3",
        embedding_openai_model_id="baai/bge-m3",
        embedding_model_ids=["text-embedding-3-small"],
    )
    pairs = _pairs(build_embedding_seed_entries(cfg))
    assert pairs["baai/bge-m3"] == "BAAI/bge-m3"
    assert pairs["text-embedding-3-small"] == "text-embedding-3-small"


def test_rerank_pairs_no_duplicate_when_openai_alias_present() -> None:
    cfg = ProviderLitserveInfraConfig(
        rerank_model_id="BAAI/bge-reranker-v2-gemma",
        rerank_openai_model_id="baai/bge-reranker-v2-gemma",
        rerank_model_ids=[],
    )
    assert _pairs(build_rerank_seed_entries(cfg)) == {
        "baai/bge-reranker-v2-gemma": "BAAI/bge-reranker-v2-gemma"
    }


def test_rerank_pairs_only_hf() -> None:
    cfg = ProviderLitserveInfraConfig(
        rerank_model_id="BAAI/bge-reranker-v2-gemma",
        rerank_openai_model_id="",
        rerank_model_ids=[],
    )
    assert _pairs(build_rerank_seed_entries(cfg)) == {
        "BAAI/bge-reranker-v2-gemma": "BAAI/bge-reranker-v2-gemma"
    }
