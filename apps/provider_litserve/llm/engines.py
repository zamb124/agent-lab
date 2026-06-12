"""Инференс локального chat LLM для POST /v1/chat/completions."""

from __future__ import annotations

import json
import time
from typing import Protocol, Self, cast

import torch
from fastapi import HTTPException
from pydantic import BaseModel, ValidationError
from transformers import AutoModelForCausalLM, AutoTokenizer

from apps.provider_litserve.openai_server_contracts import (
    OpenAIChatCompletionsRequest,
    OpenAIChatMessage,
    build_openai_chat_completions_response,
)
from apps.provider_litserve.provider_litserve_http_schemas import OpenAIChatCompletionsResponseBody
from core.config.models import ProviderLitserveInfraConfig
from core.logging import get_logger
from core.types import JsonValue

logger = get_logger(__name__)


class ChatTokenizer(Protocol):
    eos_token_id: int | None

    def apply_chat_template(
        self,
        conversation: list[dict[str, str]],
        *,
        tokenize: bool,
        add_generation_prompt: bool,
    ) -> str: ...

    def __call__(self, prompt: str, *, return_tensors: str) -> dict[str, torch.Tensor]: ...

    def decode(self, token_ids: torch.Tensor, *, skip_special_tokens: bool) -> str: ...


class ChatLanguageModel(Protocol):
    def eval(self) -> Self: ...

    def to(self, device: torch.device) -> Self: ...

    def generate(self, input_ids: torch.Tensor, **kwargs: float | int | bool | None) -> torch.Tensor: ...


class ChatTokenizerLoader(Protocol):
    def __call__(self, pretrained_model_name_or_path: str) -> ChatTokenizer: ...


class ChatModelLoader(Protocol):
    def __call__(self, pretrained_model_name_or_path: str, **kwargs: object) -> ChatLanguageModel: ...


def _require_cuda_when_selected(device: str) -> None:
    if not device.startswith("cuda"):
        return
    if not torch.cuda.is_available():
        message = (
            "provider_litserve: CUDA device для LLM недоступен (torch.cuda.is_available() == False); "
            "нужны драйвер NVIDIA, NVIDIA Container Toolkit и nvidia.com/gpu в Helm."
        )
        raise RuntimeError(message)


def parse_chat_body(raw: BaseModel | JsonValue) -> OpenAIChatCompletionsRequest:
    if isinstance(raw, BaseModel):
        raw_payload = raw.model_dump(exclude_none=True)
    else:
        raw_payload = raw
    if not isinstance(raw_payload, dict):
        raise HTTPException(status_code=422, detail="Тело запроса: ожидается JSON-объект")
    try:
        body = OpenAIChatCompletionsRequest.model_validate(raw_payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    return body


class LocalChatEngine:
    """Qwen instruct через transformers; 4-bit на CUDA, fp32 на CPU."""

    def __init__(self, cfg: ProviderLitserveInfraConfig) -> None:
        self._cfg: ProviderLitserveInfraConfig = cfg
        self._tokenizer: ChatTokenizer | None = None
        self._model: ChatLanguageModel | None = None
        self._device: str = "cpu"
        self._loaded_model_id: str | None = None

    def setup(self, device: str | None) -> None:
        if device:
            self._device = device

    def allowed_model_ids(self) -> frozenset[str]:
        return frozenset({self._cfg.llm_openai_model_id.strip()})

    def _ensure_model(self) -> tuple[ChatTokenizer, ChatLanguageModel]:
        if self._cfg.llm_backend != "transformers":
            raise RuntimeError(
                f"provider_litserve LLM backend {self._cfg.llm_backend!r} не поддерживает chat inference"
            )
        hf_model_id = self._cfg.llm_model_id.strip()
        if self._tokenizer is not None and self._model is not None and self._loaded_model_id == hf_model_id:
            return self._tokenizer, self._model
        _require_cuda_when_selected(self._device)
        logger.info("Loading chat model '%s' on '%s'", hf_model_id, self._device)
        started_at = time.monotonic()
        tokenizer_loader = cast(ChatTokenizerLoader, AutoTokenizer.from_pretrained)
        tokenizer = tokenizer_loader(hf_model_id)
        model_loader = cast(ChatModelLoader, AutoModelForCausalLM.from_pretrained)
        if self._device.startswith("cuda"):
            from transformers import BitsAndBytesConfig

            quantization_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
            )
            loaded_model = model_loader(
                hf_model_id,
                quantization_config=quantization_config,
                device_map="auto",
            )
        else:
            raw_model = model_loader(hf_model_id, torch_dtype=torch.float32)
            loaded_model = raw_model.to(torch.device(self._device))
        _ = loaded_model.eval()
        logger.info("Chat model '%s' loaded in %.2fs", hf_model_id, time.monotonic() - started_at)
        self._tokenizer = tokenizer
        self._model = loaded_model
        self._loaded_model_id = hf_model_id
        return tokenizer, loaded_model

    @staticmethod
    def _messages_to_chat(messages: list[OpenAIChatMessage]) -> list[dict[str, str]]:
        chat_messages: list[dict[str, str]] = []
        for message in messages:
            role = message.role.strip()
            if role not in {"system", "user", "assistant"}:
                raise HTTPException(status_code=422, detail=f"unsupported message role: {role!r}")
            content = message.content.strip()
            if not content:
                raise HTTPException(status_code=422, detail="message content must not be empty")
            chat_messages.append({"role": role, "content": content})
        if not chat_messages:
            raise HTTPException(status_code=422, detail="messages must not be empty")
        return chat_messages

    def chat(self, request: OpenAIChatCompletionsRequest) -> OpenAIChatCompletionsResponseBody:
        requested_model = request.model.strip()
        allowed = self.allowed_model_ids()
        if requested_model not in allowed:
            raise HTTPException(
                status_code=422,
                detail=f"unknown chat model {requested_model!r}; allowed={sorted(allowed)}",
            )
        tokenizer, model = self._ensure_model()
        chat_messages = self._messages_to_chat(request.messages)
        prompt = tokenizer.apply_chat_template(
            chat_messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = tokenizer(prompt, return_tensors="pt")
        input_ids_tensor = inputs["input_ids"]
        if self._device.startswith("cuda") and not hasattr(model, "hf_device_map"):
            input_ids_tensor = input_ids_tensor.to(self._device)
        max_new_tokens = request.max_tokens if request.max_tokens is not None else 2048
        if max_new_tokens < 1:
            raise HTTPException(status_code=422, detail="max_tokens must be >= 1")
        temperature = request.temperature if request.temperature is not None else 0.2
        if temperature < 0:
            raise HTTPException(status_code=422, detail="temperature must be >= 0")
        generation_kwargs: dict[str, float | int | bool | None] = {
            "max_new_tokens": max_new_tokens,
            "do_sample": temperature > 0,
            "pad_token_id": tokenizer.eos_token_id,
        }
        if temperature > 0:
            generation_kwargs["temperature"] = temperature
        if request.response_format is not None and request.response_format.type == "json_object":
            generation_kwargs["do_sample"] = False
        with torch.inference_mode():
            output_ids = model.generate(input_ids_tensor, **generation_kwargs)
        generated = output_ids[0, input_ids_tensor.shape[-1] :]
        content = tokenizer.decode(generated, skip_special_tokens=True).strip()
        if request.response_format is not None and request.response_format.type == "json_object":
            try:
                json.loads(content)
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"model returned invalid JSON: {exc.msg}",
                ) from exc
        canonical_model = self._cfg.llm_openai_model_id.strip()
        return build_openai_chat_completions_response(model_id=canonical_model, content=content)
