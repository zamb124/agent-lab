"""
Интеграционные тесты HTTP ``provider_litserve`` через ASGI (``httpx.ASGITransport``).

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
from typing import Any

import numpy as np
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from apps.provider_litserve.openai_server_contracts import (
    build_provider_litserve_v1_models_response,
)
from apps.provider_litserve.provider_litserve_asgi import create_provider_litserve_asgi_app
from apps.provider_litserve.main import ChatCompletionsLitAPI
from apps.provider_litserve.provider_litserve_http_schemas import (
    OpenAIEmbeddingsResponseBody,
    RerankResponseBody,
    V1ModelsResponseBody,
    validate_v1_models_response,
)
from apps.provider_litserve.runtime_models import (
    reset_runtime_catalog_for_tests,
    runtime_api_model_ids,
)
from core.config.models import ProviderLitserveInfraConfig

EMBEDDING_DIM = 4


@pytest.fixture(autouse=True)
def _reset_provider_litserve_runtime_catalog() -> None:
    reset_runtime_catalog_for_tests()
    yield
    reset_runtime_catalog_for_tests()


def _infra(**kwargs: Any) -> ProviderLitserveInfraConfig:
    return ProviderLitserveInfraConfig(**kwargs)


@pytest.fixture
def fake_sentence_transformers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Подмена загрузки ST: только ``encode`` возвращает фиксированные векторы."""

    class _SentenceTransformer:
        def __init__(self, *_a: object, **_k: object) -> None:
            pass

        def encode(self, texts: list[str], normalize_embeddings: bool = True) -> np.ndarray:
            return np.full((len(texts), EMBEDDING_DIM), 0.25, dtype=np.float64)

    mod = types.ModuleType("sentence_transformers")
    mod.SentenceTransformer = _SentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", mod)


@pytest.fixture
def provider_litserve_infra(unique_id: str) -> ProviderLitserveInfraConfig:
    return _infra(
        backend="placeholder",
        embedding_openai_model_id=f"baai/bge-m3-{unique_id}",
        embedding_model_id=f"BAAI/bge-m3-{unique_id}",
        rerank_openai_model_id=f"baai/rerank-{unique_id}",
        model_id=f"BAAI/rerank-{unique_id}",
    )


@pytest.fixture
def provider_asgi_app(
    fake_sentence_transformers: None,
    provider_litserve_infra: ProviderLitserveInfraConfig,
) -> FastAPI:
    return create_provider_litserve_asgi_app(
        cfg=provider_litserve_infra,
        embedding_dimension_for_models_list=EMBEDDING_DIM,
    )


@pytest.mark.asyncio
async def test_get_v1_models_contract(
    provider_asgi_app: FastAPI,
    provider_litserve_infra: ProviderLitserveInfraConfig,
) -> None:
    created = int(time.time())
    raw_expected = build_provider_litserve_v1_models_response(
        embedding_openai_model_id=provider_litserve_infra.embedding_openai_model_id,
        embedding_model_ids=provider_litserve_infra.embedding_model_ids,
        embedding_hf_model_id=provider_litserve_infra.embedding_model_id,
        embedding_dimension=EMBEDDING_DIM,
        embedding_context_length=8192,
        rerank_openai_model_id=provider_litserve_infra.rerank_openai_model_id,
        rerank_model_ids=provider_litserve_infra.rerank_model_ids,
        rerank_hf_model_id=provider_litserve_infra.model_id,
        rerank_context_length=8192,
        chat_model_ids=[],
        stt_model_ids=runtime_api_model_ids("stt", provider_litserve_infra),
        tts_model_ids=runtime_api_model_ids("tts", provider_litserve_infra),
        vad_model_ids=runtime_api_model_ids("vad", provider_litserve_infra),
        created=created,
    )
    expected_body = validate_v1_models_response(raw_expected)
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
    detail = r.json().get("detail")
    assert isinstance(detail, dict) and detail.get("reason") == "unknown_embedding_model"


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
    cfg = _infra(
        backend="placeholder",
        max_passages=2,
        embedding_openai_model_id=f"baai/bge-m3-{unique_id}",
        embedding_model_id=f"BAAI/bge-m3-{unique_id}",
        rerank_openai_model_id=f"baai/rerank-{unique_id}",
        model_id=f"BAAI/rerank-{unique_id}",
    )
    app = create_provider_litserve_asgi_app(
        cfg=cfg,
        embedding_dimension_for_models_list=EMBEDDING_DIM,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/v1/rerank",
            json={"query": "q", "passages": ["a", "b", "c"]},
        )
    assert r.status_code == 422
    assert r.json()["detail"]["reason"] == "too_many_passages"


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
    mod.FlagLLMReranker = _FlagLLMReranker
    monkeypatch.setitem(sys.modules, "FlagEmbedding", mod)


@pytest.mark.asyncio
async def test_post_v1_rerank_flagllm_mocked_compute_score(
    unique_id: str,
    fake_sentence_transformers: None,
    fake_flag_embedding: None,
) -> None:
    cfg = _infra(
        backend="flagllm",
        embedding_openai_model_id=f"baai/bge-m3-{unique_id}",
        embedding_model_id=f"BAAI/bge-m3-{unique_id}",
        rerank_openai_model_id=f"baai/rerank-{unique_id}",
        model_id=f"BAAI/rerank-{unique_id}",
    )
    app = create_provider_litserve_asgi_app(
        cfg=cfg,
        embedding_dimension_for_models_list=EMBEDDING_DIM,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/v1/rerank",
            json={"query": "q", "passages": ["a", "b", "c"]},
        )
    assert r.status_code == 200
    parsed = RerankResponseBody.model_validate(r.json())
    assert parsed.scores == [1.0, 0.5, 1.0 / 3]


def test_chat_completions_litapi_predict_local_model_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """ChatCompletionsLitAPI генерирует ответ локальной моделью."""

    class _FakeNoGrad:
        def __enter__(self):
            return None

        def __exit__(self, exc_type, exc_val, exc_tb):
            return None

    fake_torch = types.SimpleNamespace(no_grad=lambda: _FakeNoGrad())
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    class _FakeInputs(dict):
        def to(self, _device: str):
            return self

    class _Tokenizer:
        eos_token_id = 1

        @classmethod
        def from_pretrained(cls, *_a: object, **_k: object):
            return cls()

        def apply_chat_template(self, messages: list[dict[str, str]], tokenize: bool, add_generation_prompt: bool) -> str:
            assert tokenize is False
            assert add_generation_prompt is True
            return str(messages)

        def __call__(self, prompt: str, return_tensors: str):
            assert prompt
            assert return_tensors == "pt"
            return _FakeInputs({"input_ids": np.array([[11, 12, 13]])})

        def decode(self, output_ids: np.ndarray, skip_special_tokens: bool) -> str:
            assert skip_special_tokens is True
            assert output_ids.tolist() == [21, 22]
            return "hello local"

    class _Model:
        @classmethod
        def from_pretrained(cls, *_a: object, **_k: object):
            return cls()

        def to(self, _device: str):
            return self

        def generate(self, **_kwargs: Any):
            return [np.array([11, 12, 13, 21, 22])]

    fake_transformers = types.SimpleNamespace(
        AutoTokenizer=_Tokenizer,
        AutoModelForCausalLM=_Model,
    )
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)

    settings = types.SimpleNamespace(
        provider_litserve=types.SimpleNamespace(
            infra=types.SimpleNamespace(
                llm_model_id="Qwen/Qwen2.5-1.5B-Instruct",
                llm_model_ids=["Qwen/Qwen2.5-1.5B-Instruct"],
                markdown_default_api_model_id="Qwen/Qwen2.5-1.5B-Instruct",
                hf_token="hf_test",
            )
        )
    )

    monkeypatch.setattr("apps.provider_litserve.main.get_provider_litserve_settings", lambda: settings)

    api = ChatCompletionsLitAPI()
    api.setup("cpu")
    outputs = list(
        api.predict(
            {
                "model": "Qwen/Qwen2.5-1.5B-Instruct",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": True,
            }
        )
    )

    assert len(outputs) == 1
    out = outputs[0]
    assert out["role"] == "assistant"
    assert out["content"] == "hello local"
    assert out["prompt_tokens"] == 3
    assert out["completion_tokens"] == 2
    assert out["total_tokens"] == 5
