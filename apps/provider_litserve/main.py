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
import time
from typing import Any

import litserve as ls
from fastapi import Depends

from apps.provider_litserve.config import get_provider_litserve_settings
from apps.provider_litserve.embedding.api import EmbeddingLitAPI
from apps.provider_litserve.reranker.api import RerankerLitAPI
from apps.provider_litserve.openai_server_contracts import build_provider_litserve_v1_models_response


def _register_v1_models_route(server: ls.LitServer) -> None:
    settings = get_provider_litserve_settings()
    cfg = settings.provider_litserve.infra

    def list_models() -> dict[str, Any]:
        created = int(time.time())
        return build_provider_litserve_v1_models_response(
            embedding_openai_model_id=cfg.embedding_openai_model_id,
            embedding_hf_model_id=cfg.embedding_model_id,
            embedding_dimension=settings.rag.embedding.api.dimension,
            embedding_context_length=8192,
            rerank_openai_model_id=cfg.rerank_openai_model_id,
            rerank_hf_model_id=cfg.model_id,
            rerank_context_length=8192,
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
        [EmbeddingLitAPI(cfg), RerankerLitAPI(cfg)],
        accelerator=cfg.accelerator,
        workers_per_device=cfg.workers_per_device,
        timeout=cfg.request_timeout_seconds,
        fast_queue=cfg.fast_queue,
    )
    _register_v1_models_route(server)
    server.run(host=host, port=port, log_level="info", generate_client_file=False)


if __name__ == "__main__":
    main()
