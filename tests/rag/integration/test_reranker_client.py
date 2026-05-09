"""
Интеграция HTTP-клиента реранкера с ASGI POST ``/v1/rerank`` (RAG-60): без тихого fallback при ошибках.

Трафик: ``RerankerHTTPClient`` -> ASGI-заглушка ``rerank_v1_rerank_stub``; ответ upstream подменяется через ``Depends``.
"""

from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from core.rag.post_retrieval_rerank import RerankerClientError, RerankerHTTPClient
from core.context import clear_context, set_context
from core.models.billing_models import UsageType
from core.models.context_models import Context, Language
from core.models.identity_models import Company, User
from core.rag.models import RAGSearchResult

from .rerank_v1_rerank_stub import create_v1_rerank_stub_app, get_rerank_upstream

GATEWAY_V1_RERANK = "http://test/v1/rerank"


class _ASGIClientCM:
    """Контекстный менеджер ``get_httpx_client``: реальный HTTP к ASGI-приложению."""

    def __init__(self, app: FastAPI) -> None:
        self._app = app
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> httpx.AsyncClient:
        self._client = httpx.AsyncClient(
            transport=ASGITransport(app=self._app),
            base_url="http://test",
        )
        return self._client

    async def __aexit__(self, *args: object) -> None:
        if self._client is not None:
            await self._client.aclose()


def _install_gateway_client(monkeypatch: pytest.MonkeyPatch, app: FastAPI) -> None:
    monkeypatch.setattr(
        "core.rag.post_retrieval_rerank.get_httpx_client",
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
        async def post_predict(self, body: bytes, content_type: str) -> httpx.Response:
            return httpx.Response(200, json={"scores": [0.01, 0.99]})

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
    client = RerankerHTTPClient(timeout_seconds=30.0, billing_service=AsyncMock())
    out = await client.rerank(GATEWAY_V1_RERANK, "alpha beta", results)
    assert {
        "len": len(out),
        "first_content": out[0].content,
        "rerank": out[0].provenance.get("rerank"),
        "scores_desc": out[0].score > out[1].score,
    } == {
        "len": 2,
        "first_content": "alpha beta gamma",
        "rerank": True,
        "scores_desc": True,
    }


@pytest.mark.asyncio
async def test_rerank_reorders_by_scores(monkeypatch: pytest.MonkeyPatch) -> None:
    """Успешный ответ: порядок по убыванию scores, provenance с rerank_score."""

    class _MockUpstream:
        async def post_predict(self, body: bytes, content_type: str) -> httpx.Response:
            return httpx.Response(200, json={"scores": [0.2, 0.8]})

    app = create_v1_rerank_stub_app()
    app.dependency_overrides[get_rerank_upstream] = lambda: _MockUpstream()
    _install_gateway_client(monkeypatch, app)

    billing = AsyncMock()
    client = RerankerHTTPClient(timeout_seconds=5.0, billing_service=billing)
    out = await client.rerank(
        GATEWAY_V1_RERANK,
        "q",
        _sample_results(),
    )
    billing.record_usage.assert_awaited_once()
    assert {
        "len": len(out),
        "first_content": out[0].content,
        "second_content": out[1].content,
        "rerank": out[0].provenance.get("rerank"),
    } == {"len": 2, "first_content": "b", "second_content": "a", "rerank": True}
    assert out[0].score == pytest.approx(0.8)
    assert out[0].provenance.get("rerank_score") == pytest.approx(0.8)


@pytest.mark.asyncio
async def test_rerank_503_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """503 от upstream — RerankerClientError с status_code 503 и телом."""

    class _MockUpstream:
        async def post_predict(self, body: bytes, content_type: str) -> httpx.Response:
            return httpx.Response(503, json={"reason": "overload"})

    app = create_v1_rerank_stub_app()
    app.dependency_overrides[get_rerank_upstream] = lambda: _MockUpstream()
    _install_gateway_client(monkeypatch, app)

    client = RerankerHTTPClient(timeout_seconds=5.0, billing_service=AsyncMock())
    with pytest.raises(RerankerClientError) as ei:
        await client.rerank(GATEWAY_V1_RERANK, "q", _sample_results())
    assert ei.value.status_code == 503
    assert ei.value.detail == {"reason": "overload"}


@pytest.mark.asyncio
async def test_rerank_scores_length_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Несовпадение длины scores с passages — 422."""

    class _MockUpstream:
        async def post_predict(self, body: bytes, content_type: str) -> httpx.Response:
            return httpx.Response(200, json={"scores": [0.5]})

    app = create_v1_rerank_stub_app()
    app.dependency_overrides[get_rerank_upstream] = lambda: _MockUpstream()
    _install_gateway_client(monkeypatch, app)

    client = RerankerHTTPClient(timeout_seconds=5.0, billing_service=AsyncMock())
    with pytest.raises(RerankerClientError) as ei:
        await client.rerank(GATEWAY_V1_RERANK, "q", _sample_results())
    assert {"status_code": ei.value.status_code, "reason": ei.value.detail.get("reason")} == {
        "status_code": 422,
        "reason": "scores_length_mismatch",
    }


@pytest.mark.asyncio
async def test_rerank_billing_usage_type_and_resource(monkeypatch: pytest.MonkeyPatch) -> None:
    """При контексте user/company запись в BillingService с RERANK_REQUEST."""

    class _MockUpstream:
        async def post_predict(self, body: bytes, content_type: str) -> httpx.Response:
            return httpx.Response(200, json={"scores": [0.1, 0.9]})

    app = create_v1_rerank_stub_app()
    app.dependency_overrides[get_rerank_upstream] = lambda: _MockUpstream()
    _install_gateway_client(monkeypatch, app)

    billing = AsyncMock()
    user = User(user_id="u-rerank-bill", name="U", companies={"c1": ["admin"]}, active_company_id="c1")
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
        client = RerankerHTTPClient(
            timeout_seconds=5.0,
            billing_service=billing,
            cost_per_1m_tokens=1.0,
            platform_markup=1.0,
            billing_resource_id="bge-test",
        )
        await client.rerank(GATEWAY_V1_RERANK, "query text", _sample_results())
    finally:
        clear_context()

    billing.record_usage.assert_awaited_once()
    kwargs = billing.record_usage.await_args.kwargs
    assert {
        **{k: kwargs[k] for k in ("usage_type", "resource_name", "user", "company")},
        "quantity_positive": kwargs["quantity"] > 0,
        "cost_nonneg": kwargs["cost"] >= 0.0,
    } == {
        "usage_type": UsageType.RERANK_REQUEST,
        "resource_name": "rerank:bge-test",
        "user": user,
        "company": company,
        "quantity_positive": True,
        "cost_nonneg": True,
    }
