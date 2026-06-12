"""Resolve which LitServe worker APIs are registered in this process."""

from __future__ import annotations

from typing import Literal

from core.config.models import ProviderLitserveInfraConfig

ProviderLitserveWorkerKind = Literal["embedding", "rerank", "stt", "tts", "vad", "llm"]

_ALL_WORKERS: frozenset[ProviderLitserveWorkerKind] = frozenset(
    ("embedding", "rerank", "stt", "tts", "vad", "llm")
)


def resolved_enabled_workers(cfg: ProviderLitserveInfraConfig) -> frozenset[ProviderLitserveWorkerKind]:
    if cfg.enabled_workers:
        unknown = set(cfg.enabled_workers) - set(_ALL_WORKERS)
        if unknown:
            raise ValueError(f"unknown enabled_workers: {sorted(unknown)}")
        return frozenset(cfg.enabled_workers)
    workers: set[ProviderLitserveWorkerKind] = {"embedding", "rerank", "stt", "tts", "vad"}
    if cfg.llm_backend == "transformers":
        workers.add("llm")
    return frozenset(workers)
