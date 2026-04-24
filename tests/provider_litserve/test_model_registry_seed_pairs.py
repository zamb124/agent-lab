"""Сид реестра LitServe: без дублей по api и каноничному HF."""

from core.config.models import ProviderLitserveInfraConfig

from apps.provider_litserve.model_registry import build_embedding_api_pairs, build_rerank_api_pairs


def test_embedding_pairs_no_duplicate_hf_row_when_openai_alias_present() -> None:
    cfg = ProviderLitserveInfraConfig(
        embedding_model_id="BAAI/bge-m3",
        embedding_openai_model_id="baai/bge-m3",
        embedding_model_ids=[],
    )
    pairs = build_embedding_api_pairs(cfg)
    assert pairs == {"baai/bge-m3": "BAAI/bge-m3"}


def test_embedding_pairs_skips_case_duplicate_list_keys() -> None:
    cfg = ProviderLitserveInfraConfig(
        embedding_model_id="BAAI/bge-m3",
        embedding_openai_model_id="baai/bge-m3",
        embedding_model_ids=["BAAI/bge-m3"],
    )
    pairs = build_embedding_api_pairs(cfg)
    assert pairs == {"baai/bge-m3": "BAAI/bge-m3"}


def test_embedding_pairs_extra_model_in_list() -> None:
    cfg = ProviderLitserveInfraConfig(
        embedding_model_id="BAAI/bge-m3",
        embedding_openai_model_id="baai/bge-m3",
        embedding_model_ids=["text-embedding-3-small"],
    )
    pairs = build_embedding_api_pairs(cfg)
    assert pairs["baai/bge-m3"] == "BAAI/bge-m3"
    assert pairs["text-embedding-3-small"] == "text-embedding-3-small"


def test_rerank_pairs_no_duplicate_when_openai_alias_present() -> None:
    cfg = ProviderLitserveInfraConfig(
        model_id="BAAI/bge-reranker-v2-gemma",
        rerank_openai_model_id="baai/bge-reranker-v2-gemma",
        rerank_model_ids=[],
    )
    pairs = build_rerank_api_pairs(cfg)
    assert pairs == {"baai/bge-reranker-v2-gemma": "BAAI/bge-reranker-v2-gemma"}


def test_rerank_pairs_only_hf() -> None:
    cfg = ProviderLitserveInfraConfig(
        model_id="BAAI/bge-reranker-v2-gemma",
        rerank_openai_model_id="",
        rerank_model_ids=[],
    )
    pairs = build_rerank_api_pairs(cfg)
    assert pairs == {"BAAI/bge-reranker-v2-gemma": "BAAI/bge-reranker-v2-gemma"}
