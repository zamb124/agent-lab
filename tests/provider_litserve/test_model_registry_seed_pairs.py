"""Сид реестра LitServe: без дублей по api и каноничному HF."""

from core.config.models import ProviderLitserveInfraConfig

from apps.provider_litserve.model_registry import (
    build_embedding_api_pairs,
    build_rerank_api_pairs,
    create_or_replace_model,
    init_registry,
    list_models,
    sync_defaults_from_config,
)


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


def test_sync_defaults_adds_models_when_registry_not_empty(tmp_path) -> None:
    cfg = ProviderLitserveInfraConfig(
        sqlite_path=str(tmp_path / "registry.db"),
        llm_model_id="Qwen/Qwen2.5-1.5B-Instruct",
        llm_model_ids=["qwen/qwen2.5-1.5b-instruct"],
        embedding_model_id="Qwen/Qwen3-Embedding-4B",
        embedding_openai_model_id="qwen/qwen3-embedding-4b",
        model_id="Qwen/Qwen3-Reranker-8B",
        rerank_openai_model_id="qwen/qwen3-reranker-8b",
    )
    init_registry(cfg)
    create_or_replace_model(
        cfg,
        kind="embedding",
        hf_model_id="custom/embedding-model",
        api_model_id="custom/embedding-model",
    )

    sync_defaults_from_config(cfg)

    models = list_models(cfg)
    api_ids = {m.api_model_id for m in models}
    assert "custom/embedding-model" in api_ids
    assert "qwen/qwen2.5-1.5b-instruct" in api_ids
    assert "qwen/qwen3-embedding-4b" in api_ids
    assert "qwen/qwen3-reranker-8b" in api_ids


def test_sync_defaults_updates_existing_config_model_by_api_id(tmp_path) -> None:
    cfg = ProviderLitserveInfraConfig(
        sqlite_path=str(tmp_path / "registry.db"),
        embedding_model_id="Qwen/Qwen3-Embedding-4B",
        embedding_openai_model_id="qwen/qwen3-embedding-4b",
        model_id="Qwen/Qwen3-Reranker-8B",
        rerank_openai_model_id="qwen/qwen3-reranker-8b",
    )
    init_registry(cfg)
    create_or_replace_model(
        cfg,
        kind="llm",
        hf_model_id="Qwen/Old-Embedding",
        api_model_id="qwen/qwen3-embedding-4b",
    )

    sync_defaults_from_config(cfg)

    models = {m.api_model_id: m for m in list_models(cfg)}
    model = models["qwen/qwen3-embedding-4b"]
    assert model.kind == "embedding"
    assert model.hf_model_id == "Qwen/Qwen3-Embedding-4B"
    assert model.status == "ready"


def test_sync_defaults_is_idempotent(tmp_path) -> None:
    cfg = ProviderLitserveInfraConfig(
        sqlite_path=str(tmp_path / "registry.db"),
        llm_model_id="Qwen/Qwen2.5-1.5B-Instruct",
        llm_model_ids=["qwen/qwen2.5-1.5b-instruct"],
        embedding_model_id="Qwen/Qwen3-Embedding-4B",
        embedding_openai_model_id="qwen/qwen3-embedding-4b",
        model_id="Qwen/Qwen3-Reranker-8B",
        rerank_openai_model_id="qwen/qwen3-reranker-8b",
    )
    init_registry(cfg)

    sync_defaults_from_config(cfg)
    first_models = list_models(cfg)
    sync_defaults_from_config(cfg)
    second_models = list_models(cfg)

    assert len(second_models) == len(first_models)
    assert {m.api_model_id for m in second_models} == {m.api_model_id for m in first_models}
