"""Общие утилиты для процессов LitServe (эмбеддер и реранкер)."""

from __future__ import annotations

from core.config.models import ProviderLitserveInfraConfig


def resolve_torch_device(cfg: ProviderLitserveInfraConfig) -> str:
    acc = cfg.accelerator
    if acc == "cuda":
        return "cuda:0"
    if acc == "mps":
        return "mps"
    return "cpu"
