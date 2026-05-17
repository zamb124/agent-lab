"""Общий кеш AutoModelForCausalLM + tokenizer для эндпоинтов локального LLM.

LitServe создаёт **отдельный процесс** на каждый эндпоинт (``ChatCompletionsLitAPI``,
``MarkdownFormatLitAPI``, …). Кеш ``_models`` живёт **только в текущем процессe**:
один и тот же ``hf_model_id`` в чате и в ``format_markdown`` даст **две полные копии
весов в RAM**, если оба воркера уже дергали модель. Это ожидаемо для текущей схемы LitServe.

Внутри одного воркера повторные вызовы с тем же ``hf_model_id`` (после нормализации ключа)
переиспользуют один экземпляр.
"""

from __future__ import annotations

import os
import threading
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from core.logging import get_logger

logger = get_logger(__name__)

_cache_lock = threading.Lock()
_tokenizers: dict[str, Any] = {}
_models: dict[str, Any] = {}


def causal_lm_cache_key(hf_model_id: str) -> str:
    key = hf_model_id.strip()
    if not key:
        raise ValueError("hf_model_id пуст")
    return key


def causal_lm_load_dtype(device: str) -> torch.dtype:
    # LitServe передаёт device строкой вида ``cuda:0`` / ``mps:0``, не голый ``mps``.
    normalized = device.strip().lower()
    if normalized.startswith("cuda"):
        if torch.cuda.is_bf16_supported():
            return torch.bfloat16
        return torch.float16
    if normalized.startswith("mps"):
        return torch.float16
    return torch.float32


def ensure_local_causal_lm(
    *,
    hf_model_id: str,
    device: str,
    hf_token: str | None,
) -> tuple[Any, Any]:
    cache_key = causal_lm_cache_key(hf_model_id)
    if cache_key in _models and cache_key in _tokenizers:
        return _tokenizers[cache_key], _models[cache_key]
    with _cache_lock:
        if cache_key in _models and cache_key in _tokenizers:
            return _tokenizers[cache_key], _models[cache_key]

        if device.strip().lower().startswith("cuda") and not torch.cuda.is_available():
            raise RuntimeError(
                "provider_litserve: CUDA device для локального LLM недоступен (torch.cuda.is_available() == False); "
                "нужны драйвер NVIDIA на хосте, NVIDIA Container Toolkit и resources.limits.nvidia.com/gpu в Helm-чарте "
                "(deploy/helm/agent-lab/templates/50-gpu/litserve.yaml)."
            )
        load_kw: dict[str, Any] = {
            "token": hf_token,
            "low_cpu_mem_usage": True,
        }
        dt = causal_lm_load_dtype(device)
        if dt != torch.float32:
            load_kw["dtype"] = dt
        logger.info(
            "local_causal_lm_loading",
            hf_model_id=cache_key,
            pid=os.getpid(),
            device=device,
            dtype=str(dt),
        )
        tokenizer: Any = AutoTokenizer.from_pretrained(cache_key, token=hf_token)
        model: Any = AutoModelForCausalLM.from_pretrained(cache_key, **load_kw)
        model.to(device)
        _tokenizers[cache_key] = tokenizer
        _models[cache_key] = model
        return tokenizer, model


def reset_local_causal_lm_cache_for_tests() -> None:
    """Очищает процессный кеш моделей (только тесты)."""

    with _cache_lock:
        _tokenizers.clear()
        _models.clear()
