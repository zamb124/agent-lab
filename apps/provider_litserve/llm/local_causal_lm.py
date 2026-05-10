"""Общий кеш AutoModelForCausalLM + tokenizer для эндпоинтов локального LLM."""

from __future__ import annotations

import threading
from typing import Any

import torch

_cache_lock = threading.Lock()
_tokenizers: dict[str, Any] = {}
_models: dict[str, Any] = {}


def ensure_local_causal_lm(
    *,
    hf_model_id: str,
    device: str,
    hf_token: str | None,
) -> tuple[Any, Any]:
    if hf_model_id in _models and hf_model_id in _tokenizers:
        return _tokenizers[hf_model_id], _models[hf_model_id]
    with _cache_lock:
        if hf_model_id in _models and hf_model_id in _tokenizers:
            return _tokenizers[hf_model_id], _models[hf_model_id]
        from transformers import AutoModelForCausalLM, AutoTokenizer

        if device.startswith("cuda") and not torch.cuda.is_available():
            raise RuntimeError(
                "provider_litserve: CUDA device для локального LLM недоступен (torch.cuda.is_available() == False); "
                "нужны драйвер NVIDIA на хосте, NVIDIA Container Toolkit и resources.limits.nvidia.com/gpu в Helm-чарте "
                "(deploy/helm/agent-lab/templates/50-gpu/litserve.yaml)."
            )
        tokenizer = AutoTokenizer.from_pretrained(hf_model_id, token=hf_token)
        model = AutoModelForCausalLM.from_pretrained(hf_model_id, token=hf_token)
        model.to(device)
        _tokenizers[hf_model_id] = tokenizer
        _models[hf_model_id] = model
        return tokenizer, model


def reset_local_causal_lm_cache_for_tests() -> None:
    """Очищает процессный кеш моделей (только тесты)."""

    with _cache_lock:
        _tokenizers.clear()
        _models.clear()
