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


def resolve_embedding_device(cfg: ProviderLitserveInfraConfig, litserve_worker_device: str) -> str:
    """
    Устройство для локального эмбеддера: ``embedding_accelerator`` задаёт переопределение,
    ``auto`` совпадает с устройством воркера LitServe (``litserve_worker_device``).
    """
    ea = cfg.embedding_accelerator
    if ea == "auto":
        return litserve_worker_device
    if ea == "cpu":
        return "cpu"
    if ea == "mps":
        return "mps"
    if ea == "cuda":
        return "cuda:0"
    raise ValueError(f"unknown embedding_accelerator: {ea!r}")


def resolve_llm_device(cfg: ProviderLitserveInfraConfig, litserve_worker_device: str) -> str:
    """Устройство для локального chat LLM: ``llm_accelerator``; ``auto`` = устройство воркера."""
    la = cfg.llm_accelerator
    if la == "auto":
        return litserve_worker_device
    if la == "cpu":
        return "cpu"
    if la == "mps":
        return "mps"
    if la == "cuda":
        return "cuda:0"
    raise ValueError(f"unknown llm_accelerator: {la!r}")


def resolve_rerank_device(cfg: ProviderLitserveInfraConfig, litserve_worker_device: str) -> str:
    """Устройство для локального реранкера: ``rerank_accelerator``; ``auto`` = устройство воркера."""
    ra = cfg.rerank_accelerator
    if ra == "auto":
        return litserve_worker_device
    if ra == "cpu":
        return "cpu"
    if ra == "mps":
        return "mps"
    if ra == "cuda":
        return "cuda:0"
    raise ValueError(f"unknown rerank_accelerator: {ra!r}")
