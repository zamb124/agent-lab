"""Unit-тесты контракта TTL индексации RAG (без БД)."""

import pytest

from core.rag.ttl import ensure_ttl_seconds_in_metadata, resolve_document_ttl_seconds


def test_resolve_omitted_uses_default() -> None:
    assert resolve_document_ttl_seconds(ttl_raw=None, default_ttl_seconds=864000) == 864000


def test_resolve_zero_forever() -> None:
    assert resolve_document_ttl_seconds(ttl_raw=0, default_ttl_seconds=864000) == 0


def test_resolve_explicit_positive() -> None:
    assert resolve_document_ttl_seconds(ttl_raw=3600, default_ttl_seconds=864000) == 3600


def test_resolve_invalid_bool() -> None:
    with pytest.raises(ValueError):
        resolve_document_ttl_seconds(ttl_raw=True, default_ttl_seconds=864000)


def test_resolve_invalid_negative() -> None:
    with pytest.raises(ValueError):
        resolve_document_ttl_seconds(ttl_raw=-1, default_ttl_seconds=864000)


def test_ensure_ttl_injects_default() -> None:
    out = ensure_ttl_seconds_in_metadata({}, default_ttl_seconds=100)
    assert out["ttl_seconds"] == 100


def test_ensure_ttl_preserves_explicit_zero() -> None:
    out = ensure_ttl_seconds_in_metadata({"ttl_seconds": 0}, default_ttl_seconds=100)
    assert out["ttl_seconds"] == 0
