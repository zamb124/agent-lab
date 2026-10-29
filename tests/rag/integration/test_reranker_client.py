"""
Интеграция runtime rerank с ASGI POST ``/v1/rerank`` (RAG-60): без тихого fallback при ошибках.

Трафик: ``core.ai.runtime.rerank_scores`` -> ASGI-заглушка ``rerank_v1_rerank_stub``;
ответ upstream подменяется через ``Depends``.
"""


import httpx2
import pytest
from fastapi import FastAPI
from httpx2 import ASGITransport

import core.tracing.attributes as trace_attributes
from core.ai.rerank_client import AIRerankerClientError
from core.ai.runtime import rerank_scores
from core.context import clear_context, set_context
from core.models.billing_models import UsageType
from core.models.context_models import Context, Language
from core.models.identity_models import Company, User
from core.rag.models import RAGSearchResult
from core.tracing import setup_tracing
from core.tracing.config import TracingConfig
from core.tracing.models import Span
from core.tracing.provider import set_tracing_enabled
from core.tracing.tracer import set_tracing_service_name

from .rerank_v1_rerank_stub import create_v1_rerank_stub_app, get_rerank_upstream

GATEWAY_V1_RERANK = "http://test/v1/rerank"


class _ASGIClientCM:
    """Контекстный менеджер ``get_httpx_client``: реальный HTTP к ASGI-приложению."""

    def __init__(self, app: FastAPI) -> None:
        self._app = app
        self._client: httpx2.AsyncClient | None = None

    async def __aenter__(self) -> httpx2.AsyncClient:
        self._client = httpx2.AsyncClient(
            transport=ASGITransport(app=self._app),
            base_url="http://test",
        )
        return self._client

    async def __aexit__(self, *args: object) -> None:
        if self._client is not None:
            await self._client.aclose()


def _install_gateway_client(monkeypatch: pytest.MonkeyPatch, app: FastAPI) -> None:
    monkeypatch.setattr(
        "core.ai.rerank_client.get_httpx_client",
        lambda **kw: _ASGIClientCM(app),
    )


def _sample_results() -> list[RAGSearchResult]:
    return [
        RAGSearchResult(
            content="a",
            score=0.9,
            document_id="d1",
            document_name="n1",
            namespace="ns",
            chunk_id="c1",
            provenance={"channel": "semantic"},
        ),
        RAGSearchResult(
            content="b",
            score=0.1,
            document_id="d2",
            document_name="n2",
            namespace="ns",
            chunk_id="c2",
            provenance={"channel": "semantic"},
        ),
    ]


@pytest.mark.asyncio
async def test_rerank_reorders_by_scores_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    """Подменённый upstream: второй пассаж ранжируется выше по ``scores``."""

    class _MockUpstream:
        async def post_predict(self, body: bytes, content_type: str) -> httpx2.Response:
            return httpx2.Response(200, json={"scores": [0.01, 0.99]})

    app = create_v1_rerank_stub_app()
    app.dependency_overrides[get_rerank_upstream] = lambda: _MockUpstream()
    _install_gateway_client(monkeypatch, app)

    results = [
        RAGSearchResult(
            content="noise only",
            score=0.99,
            document_id="d1",
            document_name="n1",
            namespace="ns",
            chunk_id="c1",
            provenance={"channel": "semantic"},
        ),
        RAGSearchResult(
            content="alpha beta gamma",
            score=0.01,
            document_id="d2",
            document_name="n2",
            namespace="ns",
            chunk_id="c2",
            provenance={"channel": "semantic"},
        ),
    ]
    scores = await rerank_scores(
        endpoint_url=GATEWAY_V1_RERANK,
        query="alpha beta",
        passages=[item.content for item in results],
        timeout_seconds=30.0,
    )
    out = sorted(zip(scores, results), key=lambda item: item[0], reverse=True)
    assert {
        "len": len(out),
        "first_content": out[0][1].content,
        "scores_desc": out[0][0] > out[1][0],
    } == {
        "len": 2,
        "first_content": "alpha beta gamma",
        "scores_desc": True,
    }


@pytest.mark.asyncio
async def test_rerank_reorders_by_scores(monkeypatch: pytest.MonkeyPatch) -> None:
    """Успешный ответ: порядок по убыванию scores, provenance с rerank_score."""

    class _MockUpstream:
        async def post_predict(self, body: bytes, content_type: str) -> httpx2.Response:
            return httpx2.Response(200, json={"scores": [0.2, 0.8]})

    app = create_v1_rerank_stub_app()
    app.dependency_overrides[get_rerank_upstream] = lambda: _MockUpstream()
    _install_gateway_client(monkeypatch, app)

    scores = await rerank_scores(
        endpoint_url=GATEWAY_V1_RERANK,
        query="q",
        passages=[item.content for item in _sample_results()],
        timeout_seconds=5.0,
    )
    out = sorted(zip(scores, _sample_results()), key=lambda item: item[0], reverse=True)
    assert {
        "len": len(out),
        "first_content": out[0][1].content,
        "second_content": out[1][1].content,
    } == {"len": 2, "first_content": "b", "second_content": "a"}
    assert out[0][0] == pytest.approx(0.8)


@pytest.mark.asyncio
async def test_rerank_503_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """503 от upstream — AIRerankerClientError с status_code 503 и телом."""

    class _MockUpstream:
        async def post_predict(self, body: bytes, content_type: str) -> httpx2.Response:
            return httpx2.Response(503, json={"reason": "overload"})

    app = create_v1_rerank_stub_app()
    app.dependency_overrides[get_rerank_upstream] = lambda: _MockUpstream()
    _install_gateway_client(monkeypatch, app)

    with pytest.raises(AIRerankerClientError) as ei:
        await rerank_scores(
            endpoint_url=GATEWAY_V1_RERANK,
            query="q",
            passages=[item.content for item in _sample_results()],
            timeout_seconds=5.0,
        )
    assert ei.value.status_code == 503
    assert ei.value.detail == {"reason": "overload"}


@pytest.mark.asyncio
async def test_rerank_scores_length_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Несовпадение длины scores с passages — 422."""

    class _MockUpstream:
        async def post_predict(self, body: bytes, content_type: str) -> httpx2.Response:
            return httpx2.Response(200, json={"scores": [0.5]})

    app = create_v1_rerank_stub_app()
    app.dependency_overrides[get_rerank_upstream] = lambda: _MockUpstream()
    _install_gateway_client(monkeypatch, app)

    with pytest.raises(AIRerankerClientError) as ei:
        await rerank_scores(
            endpoint_url=GATEWAY_V1_RERANK,
            query="q",
            passages=[item.content for item in _sample_results()],
            timeout_seconds=5.0,
        )
    assert {"status_code": ei.value.status_code, "reason": ei.value.detail.get("reason")} == {
        "status_code": 422,
        "reason": "scores_length_mismatch",
    }


@pytest.mark.asyncio
async def test_rerank_billing_span_pending_settlement(
    monkeypatch: pytest.MonkeyPatch, di, unique_id: str
) -> None:
    """При контексте user/company реранк пишет span rerank.{model} с pending_settlement."""
    setup_tracing(
        TracingConfig(
            enabled=True,
            postgres_enabled=True,
            tempo_enabled=False,
            service_name="platform-test",
        )
    )
    set_tracing_service_name("platform-test")
    set_tracing_enabled(True)

    class _MockUpstream:
        async def post_predict(self, body: bytes, content_type: str) -> httpx2.Response:
            return httpx2.Response(200, json={"scores": [0.1, 0.9]})

    app = create_v1_rerank_stub_app()
    app.dependency_overrides[get_rerank_upstream] = lambda: _MockUpstream()
    _install_gateway_client(monkeypatch, app)

    user_id = f"u-rerank-bill-{unique_id}"
    user = User(user_id=user_id, name="U", companies={"c1": ["admin"]}, active_company_id="c1")
    company = Company(company_id="c1", name="C")
    set_context(
        Context(
            user=user,
            active_company=company,
            user_companies=[company],
            channel="test",
            language=Language.RU,
        )
    )
    try:
        await rerank_scores(
            endpoint_url=GATEWAY_V1_RERANK,
            query="query text",
            passages=[item.content for item in _sample_results()],
            timeout_seconds=5.0,
            billing_resource_id="bge-test",
        )
    finally:
        clear_context()

    spans = await Span.list_by_user_id_desc(user_id)
    rerank_spans = [span for span in spans if span.operation_name == "rerank.bge-test"]
    assert len(rerank_spans) == 1, [span.operation_name for span in spans]
    attributes = rerank_spans[0].attributes
    assert attributes[trace_attributes.ATTR_BILLING_PENDING_SETTLEMENT] is True
    assert attributes[trace_attributes.ATTR_BILLING_RESOURCE_NAME] == "rerank:bge-test"
    assert attributes[trace_attributes.ATTR_BILLING_USAGE_TYPE] == UsageType.RERANK_REQUEST.value
    quantity = attributes[trace_attributes.ATTR_BILLING_QUANTITY]
    assert isinstance(quantity, int) and quantity > 0
