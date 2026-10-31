"""
Интеграционные тесты HTTP ``provider_litserve`` через ASGI (``httpx2.ASGITransport``).

Приложение: ``apps.provider_litserve.provider_litserve_asgi.create_provider_litserve_asgi_app``
(те же ``EmbeddingLitAPI`` / ``RerankerLitAPI``, что и LitServe в ``main``).

Моки допустимы только на уровне **вызова нейросетевой модели**:
- эмбеддинги — подмена модуля ``sentence_transformers`` (класс ``SentenceTransformer`` и его ``encode``);
- реранк ``backend=flagllm`` — подмена ``FlagEmbedding.FlagLLMReranker`` и метода ``compute_score``.

Режим ``backend=placeholder`` для реранка модель не вызывает — мок не нужен.
"""

from __future__ import annotations

import sys
import time
import types

import numpy as np
import pytest
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

import apps.provider_litserve.embedding.engines as embedding_engines
import apps.provider_litserve.reranker.engines as reranker_engines
from apps.provider_litserve.catalog import ModelCatalog
from apps.provider_litserve.openai_server_contracts import (
    build_provider_litserve_v1_models_response,
)
from apps.provider_litserve.provider_litserve_asgi import create_provider_litserve_asgi_app
from apps.provider_litserve.provider_litserve_http_schemas import (
    OpenAIEmbeddingsResponseBody,
    RerankResponseBody,
    V1ModelsResponseBody,
)
from core.config.models import ProviderLitserveInfraConfig
from core.models.provider_litserve_model import ProviderLitserveModelPair

EMBEDDING_DIM = 4


@pytest.fixture
def fake_sentence_transformers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Подмена загрузки ST: только ``encode`` возвращает фиксированные векторы."""

    class _SentenceTransformer:
        def __init__(self, *_a: object, **_k: object) -> None:
            pass

        def encode(self, texts: list[str], normalize_embeddings: bool = True) -> np.ndarray:
            return np.full((len(texts), EMBEDDING_DIM), 0.25, dtype=np.float64)

    mod = types.ModuleType("sentence_transformers")
    setattr(mod, "SentenceTransformer", _SentenceTransformer)
    monkeypatch.setitem(sys.modules, "sentence_transformers", mod)
    monkeypatch.setattr(embedding_engines, "SentenceTransformer", _SentenceTransformer)


@pytest.fixture
def provider_litserve_infra(unique_id: str) -> ProviderLitserveInfraConfig:
    return ProviderLitserveInfraConfig(
        backend="placeholder",
        embedding_openai_model_id=f"baai/bge-m3-{unique_id}",
        embedding_model_id=f"BAAI/bge-m3-{unique_id}",
        rerank_openai_model_id=f"baai/rerank-{unique_id}",
        rerank_model_id=f"BAAI/rerank-{unique_id}",
    )


@pytest.fixture
def provider_asgi_app(
    fake_sentence_transformers: None,
    provider_litserve_infra: ProviderLitserveInfraConfig,
) -> FastAPI:
    return create_provider_litserve_asgi_app(
        cfg=provider_litserve_infra,
    )


@pytest.mark.asyncio
async def test_get_v1_models_contract(
    provider_asgi_app: FastAPI,
    provider_litserve_infra: ProviderLitserveInfraConfig,
) -> None:
    created = int(time.time())
    catalog = ModelCatalog.from_seed(provider_litserve_infra)
    expected_body = build_provider_litserve_v1_models_response(
        embedding_entries=[
            e
            for e in catalog.entries("embedding")
            if isinstance(e, ProviderLitserveModelPair)
        ],
        rerank_entries=[
            e
            for e in catalog.entries("rerank")
            if isinstance(e, ProviderLitserveModelPair)
        ],
        stt_model_ids=catalog.api_model_ids("stt"),
        tts_model_ids=catalog.api_model_ids("tts"),
        vad_model_ids=catalog.api_model_ids("vad"),
        created=created,
    )
    expected_ids = {m.id for m in expected_body.data}

    async with AsyncClient(
        transport=ASGITransport(app=provider_asgi_app),
        base_url="http://test",
    ) as client:
        r = await client.get("/v1/models")
    assert r.status_code == 200
    body = V1ModelsResponseBody.model_validate(r.json())
    assert body.object == "list"
    ids = {m.id for m in body.data}
    assert ids == expected_ids
    assert len(body.data) == len(expected_ids)


@pytest.mark.asyncio
async def test_get_health_plain_text(provider_asgi_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=provider_asgi_app),
        base_url="http://test",
    ) as client:
        r = await client.get("/health")
    assert r.status_code == 200
    assert r.text == "ok"


@pytest.mark.asyncio
async def test_post_v1_embeddings_contract_single_string(
    provider_asgi_app: FastAPI,
    provider_litserve_infra: ProviderLitserveInfraConfig,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=provider_asgi_app),
        base_url="http://test",
    ) as client:
        r = await client.post(
            "/v1/embeddings",
            json={
                "model": provider_litserve_infra.embedding_openai_model_id,
                "input": "one text",
            },
        )
    assert r.status_code == 200
    parsed = OpenAIEmbeddingsResponseBody.model_validate(r.json())
    assert parsed.model == provider_litserve_infra.embedding_openai_model_id
    assert len(parsed.data) == 1
    assert parsed.data[0].index == 0
    assert len(parsed.data[0].embedding) == EMBEDDING_DIM
    assert all(abs(x - 0.25) < 1e-9 for x in parsed.data[0].embedding)


@pytest.mark.asyncio
async def test_post_v1_embeddings_openai_extra_fields_ignored(
    provider_asgi_app: FastAPI,
    provider_litserve_infra: ProviderLitserveInfraConfig,
) -> None:
    """SDK/прокси OpenAI часто шлют encoding_format, user и др. — не должны давать 422."""
    async with AsyncClient(
        transport=ASGITransport(app=provider_asgi_app),
        base_url="http://test",
    ) as client:
        r = await client.post(
            "/v1/embeddings",
            json={
                "model": provider_litserve_infra.embedding_openai_model_id,
                "input": "x",
                "encoding_format": "float",
                "user": "ignored",
                "dimensions": 1024,
            },
        )
    assert r.status_code == 200
    parsed = OpenAIEmbeddingsResponseBody.model_validate(r.json())
    assert parsed.model == provider_litserve_infra.embedding_openai_model_id
    assert len(parsed.data) == 1


@pytest.mark.asyncio
async def test_post_v1_embeddings_contract_batch(
    provider_asgi_app: FastAPI,
    provider_litserve_infra: ProviderLitserveInfraConfig,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=provider_asgi_app),
        base_url="http://test",
    ) as client:
        r = await client.post(
            "/v1/embeddings",
            json={
                "model": provider_litserve_infra.embedding_model_id,
                "input": ["a", "b"],
            },
        )
    assert r.status_code == 200
    parsed = OpenAIEmbeddingsResponseBody.model_validate(r.json())
    assert len(parsed.data) == 2
    assert {len(row.embedding) for row in parsed.data} == {EMBEDDING_DIM}


@pytest.mark.asyncio
async def test_post_v1_embeddings_unknown_model_422(
    provider_asgi_app: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=provider_asgi_app),
        base_url="http://test",
    ) as client:
        r = await client.post(
            "/v1/embeddings",
            json={"model": "unknown/model-id", "input": "x"},
        )
    assert r.status_code == 422
    params = r.json().get("error_params")
    assert isinstance(params, dict) and params.get("reason") == "unknown_embedding_model"


@pytest.mark.asyncio
async def test_post_v1_embeddings_body_not_object_422(provider_asgi_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=provider_asgi_app),
        base_url="http://test",
    ) as client:
        r = await client.post("/v1/embeddings", json=[])
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_post_v1_rerank_placeholder_contract(
    provider_asgi_app: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=provider_asgi_app),
        base_url="http://test",
    ) as client:
        r = await client.post(
            "/v1/rerank",
            json={"query": "hello world", "passages": ["hello", "bye"]},
        )
    assert r.status_code == 200
    parsed = RerankResponseBody.model_validate(r.json())
    assert parsed.scores == [1.0, 0.0]


@pytest.mark.asyncio
async def test_post_v1_rerank_too_many_passages_422(
    unique_id: str,
    fake_sentence_transformers: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = ProviderLitserveInfraConfig(
        backend="placeholder",
        max_passages=2,
        embedding_openai_model_id=f"baai/bge-m3-{unique_id}",
        embedding_model_id=f"BAAI/bge-m3-{unique_id}",
        rerank_openai_model_id=f"baai/rerank-{unique_id}",
        rerank_model_id=f"BAAI/rerank-{unique_id}",
    )
    app = create_provider_litserve_asgi_app(
        cfg=cfg,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/v1/rerank",
            json={"query": "q", "passages": ["a", "b", "c"]},
        )
    assert r.status_code == 422
    assert r.json()["error_params"]["reason"] == "too_many_passages"


@pytest.mark.asyncio
async def test_post_v1_rerank_invalid_body_422(provider_asgi_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=provider_asgi_app),
        base_url="http://test",
    ) as client:
        r = await client.post("/v1/rerank", json={"query": "q", "passages": [], "extra": 1})
    assert r.status_code == 422


@pytest.fixture
def fake_flag_embedding(monkeypatch: pytest.MonkeyPatch) -> None:
    """Подмена FlagLLM: только ``compute_score`` задаёт скоры."""

    class _FlagLLMReranker:
        def __init__(self, *_a: object, **_k: object) -> None:
            pass

        def compute_score(
            self,
            pairs: list[tuple[str, str]],
            batch_size: int | None = None,
            max_length: int | None = None,
        ) -> list[float]:
            return [1.0 / (1 + i) for i in range(len(pairs))]

    mod = types.ModuleType("FlagEmbedding")
    setattr(mod, "FlagLLMReranker", _FlagLLMReranker)
    monkeypatch.setitem(sys.modules, "FlagEmbedding", mod)
    monkeypatch.setattr(reranker_engines, "FlagLLMReranker", _FlagLLMReranker)


@pytest.mark.asyncio
async def test_post_v1_rerank_flagllm_mocked_compute_score(
    unique_id: str,
    fake_sentence_transformers: None,
    fake_flag_embedding: None,
) -> None:
    cfg = ProviderLitserveInfraConfig(
        backend="flagllm",
        embedding_openai_model_id=f"baai/bge-m3-{unique_id}",
        embedding_model_id=f"BAAI/bge-m3-{unique_id}",
        rerank_openai_model_id=f"baai/rerank-{unique_id}",
        rerank_model_id=f"BAAI/rerank-{unique_id}",
    )
    app = create_provider_litserve_asgi_app(
        cfg=cfg,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/v1/rerank",
            json={"query": "q", "passages": ["a", "b", "c"]},
        )
    assert r.status_code == 200
    parsed = RerankResponseBody.model_validate(r.json())
    assert parsed.scores == [1.0, 0.5, 1.0 / 3]
