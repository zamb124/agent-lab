"""Резолв устройства для LitServe при accelerator=auto."""

from __future__ import annotations

from core.config.models import ProviderLitserveInfraConfig
from apps.provider_litserve import shared as pl_shared


def test_resolve_explicit_cuda():
    cfg = ProviderLitserveInfraConfig(accelerator="cuda")
    assert pl_shared.resolve_torch_device(cfg) == "cuda:0"


def test_resolve_explicit_cpu():
    cfg = ProviderLitserveInfraConfig(accelerator="cpu")
    assert pl_shared.resolve_torch_device(cfg) == "cpu"


def test_resolve_auto_cuda(monkeypatch):
    monkeypatch.setattr(pl_shared.torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(pl_shared.torch.backends.mps, "is_available", lambda: False)
    cfg = ProviderLitserveInfraConfig(accelerator="auto")
    assert pl_shared.resolve_torch_device(cfg) == "cuda:0"


def test_resolve_auto_cpu(monkeypatch):
    monkeypatch.setattr(pl_shared.torch.cuda, "is_available", lambda: False)
    monkeypatch.setattr(pl_shared.torch.backends.mps, "is_available", lambda: False)
    cfg = ProviderLitserveInfraConfig(accelerator="auto")
    assert pl_shared.resolve_torch_device(cfg) == "cpu"


def test_resolve_embedding_device_override_cpu_follows_global_cuda():
    cfg = ProviderLitserveInfraConfig(accelerator="auto", embedding_accelerator="cpu")
    assert pl_shared.resolve_embedding_device(cfg, "cuda:0") == "cpu"


def test_resolve_embedding_device_auto_matches_worker():
    cfg = ProviderLitserveInfraConfig(accelerator="auto", embedding_accelerator="auto")
    assert pl_shared.resolve_embedding_device(cfg, "cuda:0") == "cuda:0"
