"""Общие утилиты для процессов LitServe (эмбеддер и реранкер)."""

from __future__ import annotations

import torch

from core.config.models import ProviderLitserveInfraConfig


def resolve_torch_device(cfg: ProviderLitserveInfraConfig) -> str:
    acc = cfg.accelerator
    if acc == "cuda":
        return "cuda:0"
    if acc == "mps":
        return "mps"
    if acc == "auto":
        if torch.cuda.is_available():
            return "cuda:0"
        if torch.backends.mps.is_available():
            return "mps"
        return "cpu"
    return "cpu"
