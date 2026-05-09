"""
In-process ASGI-приложение ``provider_litserve`` с явными контрактами OpenAPI.

Обработчики вызывают те же ``EmbeddingLitAPI`` / ``RerankerLitAPI``, что и LitServe
в ``main``; отличие — нет очередей воркеров (один процесс).

Продакшен: ``python -m apps.provider_litserve.main`` (``LitServer``).
"""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import Body, FastAPI
from fastapi.responses import PlainTextResponse

from apps.provider_litserve.embedding.api import EmbeddingLitAPI
from apps.provider_litserve.openai_server_contracts import (
    OpenAIEmbeddingsRequest,
    RerankQueryPassagesRequest,
    build_provider_litserve_v1_models_response,
)
from apps.provider_litserve.provider_litserve_http_schemas import (
    OpenAIEmbeddingsResponseBody,
    RerankResponseBody,
    V1ModelsResponseBody,
    validate_embeddings_response,
    validate_rerank_response,
    validate_v1_models_response,
)
from apps.provider_litserve.reranker.api import RerankerLitAPI
from apps.provider_litserve.runtime_models import runtime_api_model_ids
from core.config.models import ProviderLitserveInfraConfig


def create_provider_litserve_asgi_app(
    *,
    cfg: ProviderLitserveInfraConfig,
    embedding_dimension_for_models_list: int,
) -> FastAPI:
    """
    Собирает FastAPI с маршрутами ``/v1/models``, ``/health``, ``/v1/embeddings``, ``/v1/rerank``.

    ``embedding_dimension_for_models_list`` — размерность вектора в метаданных GET ``/v1/models``
    (в ``main`` берётся из ``settings.rag.embedding.api.dimension``).
    """
    embed_api = EmbeddingLitAPI(cfg)
    embed_api.setup("cpu")
    rerank_api = RerankerLitAPI(cfg)
    rerank_api.setup("cpu")

    app = FastAPI(
        title="provider_litserve",
        version="1.0.0",
        description=(
            "Локальный OpenAI-совместимый контур для RAG: эмбеддинги (POST /v1/embeddings) "
            "и реранк (POST /v1/rerank). Контракты тел и ответов зафиксированы в OpenAPI "
            "(схемы в ``provider_litserve_http_schemas`` и ``openai_server_contracts``). "
            "Продакшен — LitServe: ``apps.provider_litserve.main``."
        ),
    )

    @app.get(
        "/v1/models",
        response_model=V1ModelsResponseBody,
        tags=["provider_litserve"],
        summary="Список моделей (форма OpenRouter)",
        response_description="Записи моделей эмбеддингов, реранка и чата.",
    )
    def get_v1_models() -> V1ModelsResponseBody:
        created = int(time.time())
        raw = build_provider_litserve_v1_models_response(
            embedding_openai_model_id=cfg.embedding_openai_model_id,
            embedding_model_ids=cfg.embedding_model_ids,
            embedding_hf_model_id=cfg.embedding_model_id,
            embedding_dimension=embedding_dimension_for_models_list,
            embedding_context_length=8192,
            rerank_openai_model_id=cfg.rerank_openai_model_id,
            rerank_model_ids=cfg.rerank_model_ids,
            rerank_hf_model_id=cfg.model_id,
            rerank_context_length=8192,
            chat_model_ids=[],
            stt_model_ids=runtime_api_model_ids("stt", cfg),
            tts_model_ids=runtime_api_model_ids("tts", cfg),
            vad_model_ids=runtime_api_model_ids("vad", cfg),
            created=created,
        )
        return validate_v1_models_response(raw)

    @app.get(
        "/health",
        response_class=PlainTextResponse,
        tags=["provider_litserve"],
        summary="Проверка доступности",
        response_description="Текст ``ok`` при готовности (для in-process всегда после старта приложения).",
    )
    def get_health() -> PlainTextResponse:
        return PlainTextResponse("ok", status_code=200)

    @app.post(
        "/v1/embeddings",
        response_model=OpenAIEmbeddingsResponseBody,
        tags=["provider_litserve"],
        summary="Векторизация текстов (OpenAI-совместимое тело и ответ)",
        response_description="Поле ``model`` — канонический ``embedding_openai_model_id`` из конфигурации.",
    )
    def post_v1_embeddings(
        body: Annotated[
            OpenAIEmbeddingsRequest,
            Body(
                openapi_examples={
                    "single": {
                        "summary": "Один текст",
                        "value": {"model": "qwen/qwen3-embedding-4b", "input": "пример"},
                    },
                    "batch": {
                        "summary": "Несколько текстов",
                        "value": {"model": "qwen/qwen3-embedding-4b", "input": ["a", "b"]},
                    },
                },
            ),
        ],
    ) -> OpenAIEmbeddingsResponseBody:
        batch = embed_api.decode_request(body.model_dump())
        out = embed_api.predict(batch)
        payload = embed_api.encode_response(out)
        if not isinstance(payload, dict):
            raise TypeError("encode_response эмбеддингов должен возвращать dict для JSON")
        return validate_embeddings_response(payload)

    @app.post(
        "/v1/rerank",
        response_model=RerankResponseBody,
        tags=["provider_litserve"],
        summary="Реранк по запросу и пассажам",
        response_description="``scores[i]`` соответствует ``passages[i]``.",
    )
    def post_v1_rerank(
        body: Annotated[
            RerankQueryPassagesRequest,
            Body(
                openapi_examples={
                    "default": {
                        "summary": "Два пассажа",
                        "value": {"query": "hello", "passages": ["hello world", "bye"]},
                    },
                },
            ),
        ],
    ) -> RerankResponseBody:
        batch = rerank_api.decode_request(body.model_dump())
        out = rerank_api.predict(batch)
        payload = rerank_api.encode_response(out)
        if not isinstance(payload, dict):
            raise TypeError("encode_response реранкера должен возвращать dict для JSON")
        return validate_rerank_response(payload)

    return app
