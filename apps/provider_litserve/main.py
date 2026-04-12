"""
Точка входа: LitServer с эмбеддингами и реранком на одном HTTP-порту.

GET ``/v1/models`` — OpenRouter-подобный список моделей.
POST ``/v1/embeddings``, POST ``/v1/rerank`` — инференс во воркерах LitServe.
GET ``/health`` — встроенный LitServe (текст ``ok`` / ``not ready``).

Запуск: ``uv run --group reranker-model python scripts/run.py provider-litserve``
или ``python -m apps.provider_litserve.main``.

ASGI с зафиксированными схемами OpenAPI (тесты, не воркеры): ``apps.provider_litserve.provider_litserve_asgi.create_provider_litserve_asgi_app``.
"""

from __future__ import annotations

import argparse
import os
import time
from typing import Any

import litserve as ls
from fastapi import Depends
from fastapi import HTTPException

from apps.provider_litserve.config import get_provider_litserve_settings
from apps.provider_litserve.embedding.api import EmbeddingLitAPI
from apps.provider_litserve.reranker.api import RerankerLitAPI
from apps.provider_litserve.openai_server_contracts import build_provider_litserve_v1_models_response


class ChatCompletionsLitAPI(ls.LitAPI):
    """Локальный `/v1/chat/completions` через встроенный LitServe OpenAISpec."""

    def __init__(self) -> None:
        super().__init__(spec=ls.OpenAISpec())
        self._tokenizer: Any = None
        self._model: Any = None
        self._device: str = "cpu"
        self._max_new_tokens: int = 256
        self._allowed_models: frozenset[str] = frozenset()
        self._loaded_model_id: str = ""

    def setup(self, device) -> None:
        settings = get_provider_litserve_settings()
        infra = settings.provider_litserve.infra
        configured_ids = [mid.strip() for mid in infra.llm_model_ids if mid.strip()]
        if not configured_ids:
            configured_ids = [infra.llm_model_id.strip()]
        self._allowed_models = frozenset(configured_ids)
        self._loaded_model_id = infra.llm_model_id.strip()
        if device:
            self._device = str(device)
        hf_token = infra.hf_token if infra.hf_token else os.getenv("HF_TOKEN")
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as e:
            raise RuntimeError(
                "Локальный chat backend: установите зависимости transformers (uv sync --group reranker-model)"
            ) from e

        self._tokenizer = AutoTokenizer.from_pretrained(self._loaded_model_id, token=hf_token)
        self._model = AutoModelForCausalLM.from_pretrained(self._loaded_model_id, token=hf_token)
        self._model.to(self._device)

    def decode_request(self, request):
        return request.model_dump(exclude_none=True)

    def predict(self, request):
        if self._model is None or self._tokenizer is None:
            raise HTTPException(status_code=503, detail="chat backend is not initialized")

        body = dict(request)
        requested_model = str(body.get("model", "")).strip()
        if requested_model not in self._allowed_models:
            raise HTTPException(
                status_code=422,
                detail={
                    "reason": "unknown_chat_model",
                    "model": requested_model,
                    "allowed": sorted(self._allowed_models),
                },
            )

        messages = body.get("messages")
        if not isinstance(messages, list) or not messages:
            raise HTTPException(status_code=422, detail={"reason": "messages_required"})

        try:
            import torch
        except ImportError as e:
            raise RuntimeError("Локальный chat backend требует torch") from e

        prompt = self._tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        model_inputs = self._tokenizer(prompt, return_tensors="pt").to(self._device)
        input_tokens = int(model_inputs["input_ids"].shape[1])
        with torch.no_grad():
            generated = self._model.generate(
                **model_inputs,
                max_new_tokens=self._max_new_tokens,
                do_sample=False,
                pad_token_id=self._tokenizer.eos_token_id,
            )
        output_ids = generated[0][input_tokens:]
        content = self._tokenizer.decode(output_ids, skip_special_tokens=True).strip()
        completion_tokens = int(output_ids.shape[0])
        encoded: dict[str, Any] = {
            "role": "assistant",
            "content": content,
            "prompt_tokens": input_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": input_tokens + completion_tokens,
        }
        yield encoded


def _register_root_route(server: ls.LitServer) -> None:
    def index() -> dict[str, str]:
        return {
            "service": "provider_litserve",
            "health": "/health",
            "models": "/v1/models",
            "embeddings": "/v1/embeddings",
            "rerank": "/v1/rerank",
        }

    server.app.add_api_route("/", index, methods=["GET"])


def _register_v1_models_route(server: ls.LitServer) -> None:
    settings = get_provider_litserve_settings()
    cfg = settings.provider_litserve.infra

    def list_models() -> dict[str, Any]:
        created = int(time.time())
        chat_model_ids = [mid.strip() for mid in cfg.llm_model_ids if mid.strip()]
        if not chat_model_ids:
            chat_model_ids = [cfg.llm_model_id.strip()]
        return build_provider_litserve_v1_models_response(
            embedding_openai_model_id=cfg.embedding_openai_model_id,
            embedding_model_ids=cfg.embedding_model_ids,
            embedding_hf_model_id=cfg.embedding_model_id,
            embedding_dimension=settings.rag.embedding.api.dimension,
            embedding_context_length=8192,
            rerank_openai_model_id=cfg.rerank_openai_model_id,
            rerank_model_ids=cfg.rerank_model_ids,
            rerank_hf_model_id=cfg.model_id,
            rerank_context_length=8192,
            chat_model_ids=chat_model_ids,
            created=created,
        )

    server.app.add_api_route(
        "/v1/models",
        list_models,
        methods=["GET"],
        dependencies=[Depends(server.setup_auth())],
    )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=None)
    p.add_argument("--host", type=str, default=None)
    a = p.parse_args()

    settings = get_provider_litserve_settings()
    cfg = settings.provider_litserve.infra
    port = a.port if a.port is not None else cfg.gateway_port
    host = a.host if a.host is not None else cfg.host

    server = ls.LitServer(
        [EmbeddingLitAPI(cfg), RerankerLitAPI(cfg), ChatCompletionsLitAPI()],
        accelerator=cfg.accelerator,
        workers_per_device=cfg.workers_per_device,
        timeout=cfg.request_timeout_seconds,
        fast_queue=cfg.fast_queue,
    )
    _register_root_route(server)
    _register_v1_models_route(server)
    server.run(host=host, port=port, log_level="info", generate_client_file=False)


if __name__ == "__main__":
    main()
