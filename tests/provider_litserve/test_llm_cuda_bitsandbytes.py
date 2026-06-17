"""CUDA chat LLM requires bitsandbytes in GPU runtime."""

from __future__ import annotations

import importlib.metadata

import pytest

from apps.provider_litserve.llm import engines


def test_require_bitsandbytes_for_cuda_quant_noop_on_cpu() -> None:
    engines._require_bitsandbytes_for_cuda_quant("cpu")


def test_require_bitsandbytes_for_cuda_quant_raises_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_not_found(_name: str) -> str:
        raise importlib.metadata.PackageNotFoundError("bitsandbytes")

    monkeypatch.setattr(importlib.metadata, "version", _raise_not_found)
    with pytest.raises(RuntimeError, match="bitsandbytes"):
        engines._require_bitsandbytes_for_cuda_quant("cuda:0")
