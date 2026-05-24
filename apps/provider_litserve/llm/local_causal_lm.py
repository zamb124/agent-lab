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
from collections.abc import ItemsView, Mapping, Sequence
from typing import Literal, Protocol, TypeAlias, cast, overload

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, GenerationConfig
from transformers.generation import GenerationMixin
from transformers.generation.utils import (
    GenerateBeamDecoderOnlyOutput,
    GenerateBeamEncoderDecoderOutput,
    GenerateDecoderOnlyOutput,
    GenerateEncoderDecoderOutput,
)

from core.logging import get_logger

logger = get_logger(__name__)

_cache_lock = threading.Lock()


class CausalLMTokenizer(Protocol):
    padding_side: str
    pad_token_id: int | None
    eos_token_id: int | None

    def apply_chat_template(
        self,
        conversation: Sequence[Mapping[str, str]],
        *,
        tokenize: Literal[False],
        add_generation_prompt: bool,
    ) -> str: ...

    @overload
    def __call__(
        self,
        text: Sequence[str],
        *,
        add_special_tokens: bool,
        truncation: bool,
    ) -> Mapping[str, list[list[int]]]: ...

    @overload
    def __call__(
        self,
        text: Sequence[str],
        *,
        return_tensors: Literal["pt"],
        padding: bool,
        truncation: bool,
        max_length: int,
    ) -> "CausalLMTensorBatch": ...

    @overload
    def __call__(
        self,
        text: str,
        *,
        return_tensors: Literal["pt"],
    ) -> "CausalLMTensorBatch": ...

    def decode(self, token_ids: torch.Tensor, *, skip_special_tokens: bool) -> str: ...


class CausalLMTensorBatch(Protocol):
    def to(self, device: str) -> "CausalLMTensorBatch": ...

    def __getitem__(self, key: str) -> torch.Tensor: ...

    def get(self, key: str) -> torch.Tensor | None: ...

    def items(self) -> ItemsView[str, torch.Tensor]: ...


CausalLMGenerateOutput: TypeAlias = (
    torch.Tensor
    | GenerateDecoderOnlyOutput
    | GenerateEncoderDecoderOutput
    | GenerateBeamDecoderOnlyOutput
    | GenerateBeamEncoderDecoderOutput
)


class CausalLMModel(Protocol):
    generation_config: GenerationConfig

    def generate(
        self,
        inputs: torch.Tensor | None = None,
        *,
        attention_mask: torch.Tensor | None = None,
        token_type_ids: torch.Tensor | None = None,
        generation_config: GenerationConfig | None = None,
        max_new_tokens: int | None = None,
        do_sample: bool | None = None,
        pad_token_id: int | None = None,
    ) -> CausalLMGenerateOutput: ...


_tokenizers: dict[str, CausalLMTokenizer] = {}
_models: dict[str, CausalLMModel] = {}


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


def require_causal_lm_generated_tensor(output: CausalLMGenerateOutput) -> torch.Tensor:
    if isinstance(output, torch.Tensor):
        return output
    raise TypeError("Causal LM generate must return a token tensor")


def ensure_local_causal_lm(
    *,
    hf_model_id: str,
    device: str,
    hf_token: str | None,
) -> tuple[CausalLMTokenizer, CausalLMModel]:
    cache_key = causal_lm_cache_key(hf_model_id)
    if cache_key in _models and cache_key in _tokenizers:
        return _tokenizers[cache_key], _models[cache_key]
    with _cache_lock:
        if cache_key in _models and cache_key in _tokenizers:
            return _tokenizers[cache_key], _models[cache_key]

        if device.strip().lower().startswith("cuda") and not torch.cuda.is_available():
            message = (
                "provider_litserve: CUDA device для локального LLM недоступен (torch.cuda.is_available() == False); "
                "нужны драйвер NVIDIA на хосте, NVIDIA Container Toolkit и resources.limits.nvidia.com/gpu в Helm-чарте "
                "(deploy/helm/agent-lab/templates/50-gpu/litserve.yaml)."
            )
            raise RuntimeError(
                message
            )
        load_kw: dict[str, str | bool | torch.dtype | None] = {
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
        tokenizer = cast(CausalLMTokenizer, AutoTokenizer.from_pretrained(cache_key, token=hf_token))
        loaded_model = AutoModelForCausalLM.from_pretrained(cache_key, **load_kw)
        _ = torch.nn.Module.to(loaded_model, torch.device(device))
        model = cast(CausalLMModel, cast(GenerationMixin, loaded_model))
        _tokenizers[cache_key] = tokenizer
        _models[cache_key] = model
        return tokenizer, model


def reset_local_causal_lm_cache_for_tests() -> None:
    """Очищает процессный кеш моделей (только тесты)."""

    with _cache_lock:
        _tokenizers.clear()
        _models.clear()
