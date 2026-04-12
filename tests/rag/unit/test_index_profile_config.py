"""
Инварианты JSON-конфигурации index_profile (IndexProfileConfig).
"""

from typing import Any

import pytest
from pydantic import ValidationError

from core.rag_indexing_schema import (
    IndexProfileConfig,
    IndexProfileSplitConfig,
)


def _indexing_materialization_config_dict(cfg: dict[str, Any]) -> dict[str, Any]:
    full = IndexProfileConfig.model_validate(cfg)
    return {
        "split": full.split.model_dump(mode="json"),
        "parsing": full.parsing.model_dump(mode="json"),
        "lexical": full.lexical.model_dump(mode="json"),
    }


def _indexing_config_requires_reindex(old: dict[str, Any], new: dict[str, Any]) -> bool:
    return _indexing_materialization_config_dict(old) != _indexing_materialization_config_dict(new)


def test_index_profile_config_defaults_roundtrip() -> None:
    """Пустой объект нормализуется в дефолты; сериализация стабильна для контракта."""
    cfg = IndexProfileConfig.model_validate({})
    dumped = cfg.model_dump(mode="json")
    restored = IndexProfileConfig.model_validate(dumped)
    assert {
        "restored_eq_cfg": restored == cfg,
        "split_strategy": cfg.split.strategy,
        "parsing_engine": cfg.parsing.engine,
        "lexical_enabled": cfg.lexical.enabled,
    } == {
        "restored_eq_cfg": True,
        "split_strategy": "fixed_tokens",
        "parsing_engine": "unstructured",
        "lexical_enabled": False,
    }


def test_split_chunk_size_must_be_positive() -> None:
    """chunk_size > 0 — без подстановки «как получится»."""
    with pytest.raises(ValidationError):
        IndexProfileSplitConfig.model_validate({"chunk_size": 0})


def test_rejects_embedding_key() -> None:
    """embedding не хранится в профиле — лишний ключ ломает валидацию."""
    with pytest.raises(ValidationError) as exc:
        IndexProfileConfig.model_validate(
            {
                "embedding": {"model": "x", "dimension": 1024},
            }
        )
    err = str(exc.value).lower()
    assert "embedding" in err or "extra" in err


def test_search_defaults_rrf_k_positive_when_set() -> None:
    """rrf_k при указании должен быть > 0."""
    IndexProfileConfig.model_validate(
        {
            "search_defaults": {"rrf_k": 60},
        }
    )
    with pytest.raises(ValidationError):
        IndexProfileConfig.model_validate(
            {
                "search_defaults": {"rrf_k": 0},
            }
        )


def test_indexing_materialization_ignores_search_defaults() -> None:
    """search_defaults не входит в материализацию — смена не требует reindex."""
    base = IndexProfileConfig().model_dump(mode="json")
    merged = {
        **base,
        "search_defaults": {
            "channels": {"semantic": True, "lexical": True},
        },
    }
    only_search = IndexProfileConfig.model_validate(merged).model_dump(mode="json")
    assert _indexing_materialization_config_dict(base) == _indexing_materialization_config_dict(
        only_search
    )
    assert not _indexing_config_requires_reindex(base, only_search)


def test_split_change_requires_reindex() -> None:
    a = IndexProfileConfig().model_dump(mode="json")
    cfg = IndexProfileConfig.model_validate(a)
    new_split = cfg.split.model_copy(update={"chunk_size": 256})
    b_dict = cfg.model_copy(update={"split": new_split}).model_dump(mode="json")
    assert _indexing_config_requires_reindex(a, b_dict)
