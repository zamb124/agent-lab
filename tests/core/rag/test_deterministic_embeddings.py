"""Детерминированные эмбеддинги включаются флагом rag.embedding.mock."""

import pytest

from core.config.base import BaseSettings
from core.rag.providers.pgvector_provider import deterministic_embeddings_enabled


def test_rag_embedding_mock_reads_nested_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG__EMBEDDING__MOCK", "true")
    assert BaseSettings().rag.embedding.mock is True


def test_rag_embedding_mock_defaults_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RAG__EMBEDDING__MOCK", raising=False)
    assert BaseSettings().rag.embedding.mock is False


def test_deterministic_embeddings_enabled_in_pytest() -> None:
    assert deterministic_embeddings_enabled() is True
