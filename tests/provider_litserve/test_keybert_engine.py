"""Tests for KeyBERT LitServe engine."""

from __future__ import annotations

from apps.provider_litserve.keybert.engines import (
    KeybertExtractRequest,
    LocalKeybertEngine,
    placeholder_keybert_keywords,
)
from core.config.models import ProviderLitserveInfraConfig


def test_placeholder_keybert_keywords_mixed_ru_en() -> None:
    text = "Kubernetes Ingress настройка TLS cert-manager для кластера"
    items = placeholder_keybert_keywords(text, top_n=10)
    terms = {item.term.lower() for item in items}
    assert "kubernetes" in terms
    assert "ingress" in terms or "tls" in terms


def test_local_keybert_engine_placeholder_backend() -> None:
    cfg = ProviderLitserveInfraConfig(keybert_backend="placeholder")
    engine = LocalKeybertEngine(cfg)
    engine.setup("cpu")
    response = engine.extract(
        KeybertExtractRequest(
            text="CVE-2024-9999 OpenSSL vulnerability patch",
            top_n=5,
        )
    )
    assert response.model == cfg.keybert_openai_model_id
    assert len(response.keywords) > 0
