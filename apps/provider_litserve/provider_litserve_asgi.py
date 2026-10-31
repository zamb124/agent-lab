"""
In-process ASGI-приложение ``provider_litserve`` с явными контрактами OpenAPI.

Обработчики RAG вызывают те же ``EmbeddingLitAPI`` / ``RerankerLitAPI``, что и LitServe
в ``main``; отличие — нет очередей воркеров (один процесс) и каталог моделей —
``ModelCatalog.from_seed`` из конфига, без Postgres. Speech-модели отражаются
в ``/v1/models`` как часть production-каталога, но in-process ASGI содержит только
RAG endpoints.

Продакшен: ``python -m apps.provider_litserve.main`` (``LitServer``).
"""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import Body, FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from apps.provider_litserve.catalog import ModelCatalog
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
)
from apps.provider_litserve.reranker.api import RerankerLitAPI
from core.config.models import ProviderLitserveInfraConfig
from core.models.provider_litserve_model import (
    LitserveModelKind,
    ProviderLitserveModelPair,
)
from core.websocket import WsCommandError, command_failure_payload, ws_command_error_status


def create_provider_litserve_asgi_app(
    *,
    cfg: ProviderLitserveInfraConfig,
) -> FastAPI:
    """
    Собирает FastAPI с маршрутами ``/v1/models``, ``/health``, ``/v1/embeddings``, ``/v1/rerank``.
    """
    catalog = ModelCatalog.from_seed(cfg)
    embed_api = EmbeddingLitAPI(cfg, catalog)
    embed_api.setup("cpu")
    rerank_api = RerankerLitAPI(cfg, catalog)
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

    def _pairs(kind: LitserveModelKind) -> list[ProviderLitserveModelPair]:
        return [
            entry
            for entry in catalog.entries(kind)
            if isinstance(entry, ProviderLitserveModelPair)
        ]

    def get_v1_models() -> V1ModelsResponseBody:
        created = int(time.time())
        return build_provider_litserve_v1_models_response(
            embedding_entries=_pairs("embedding"),
            rerank_entries=_pairs("rerank"),
            stt_model_ids=catalog.api_model_ids("stt"),
            tts_model_ids=catalog.api_model_ids("tts"),
            vad_model_ids=catalog.api_model_ids("vad"),
            created=created,
        )

    _ = app.get(
        "/v1/models",
        response_model=V1ModelsResponseBody,
        tags=["provider_litserve"],
        summary="Список моделей (форма OpenRouter)",
        response_description="Записи моделей эмбеддингов, реранка и речи.",
    )(get_v1_models)

    def get_health() -> PlainTextResponse:
        return PlainTextResponse("ok", status_code=200)

    _ = app.get(
        "/health",
        response_class=PlainTextResponse,
        tags=["provider_litserve"],
        summary="Проверка доступности",
        response_description="Текст ``ok`` при готовности (для in-process всегда после старта приложения).",
    )(get_health)

    def post_v1_embeddings(
        body: Annotated[
            OpenAIEmbeddingsRequest,
            Body(
                openapi_examples={
                    "single": {
                        "summary": "Один текст",
                        "value": {"model": "qwen/qwen3-embedding-0.6b", "input": "пример"},
                    },
                    "batch": {
                        "summary": "Несколько текстов",
                        "value": {"model": "qwen/qwen3-embedding-0.6b", "input": ["a", "b"]},
                    },
                },
            ),
        ],
    ) -> OpenAIEmbeddingsResponseBody:
        batch = embed_api.decode_request(body.model_dump())
        out = embed_api.predict(batch)
        return embed_api.encode_response(out)

    _ = app.post(
        "/v1/embeddings",
        response_model=OpenAIEmbeddingsResponseBody,
        tags=["provider_litserve"],
        summary="Векторизация текстов (OpenAI-совместимое тело и ответ)",
        response_description="Поле ``model`` — канонический ``embedding_openai_model_id`` из конфигурации.",
    )(post_v1_embeddings)

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
        return rerank_api.encode_response(out)

    _ = app.post(
        "/v1/rerank",
        response_model=RerankResponseBody,
        tags=["provider_litserve"],
        summary="Реранк по запросу и пассажам",
        response_description="``scores[i]`` соответствует ``passages[i]``.",
    )(post_v1_rerank)

    @app.exception_handler(WsCommandError)
    async def _ws_command_error_handler(
        _request: Request, exc: WsCommandError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=ws_command_error_status(exc),
            content=command_failure_payload(exc),
        )

    _ = _ws_command_error_handler

    return app
