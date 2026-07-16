"""Tests for runet_discover flow tool — Phase 2 discovery mode."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.flows.tools.builtin_specs import BUILTIN_TOOL_SPECS
from apps.flows.tools.index_search import RunetDiscoverToolArgs, _runet_discover_impl


def test_runet_discover_registered_in_builtin_specs() -> None:
    specs = {(module, attr) for module, attr in BUILTIN_TOOL_SPECS}
    assert ("apps.flows.tools.index_search", "runet_discover") in specs


def test_runet_discover_args_model_defaults() -> None:
    args = RunetDiscoverToolArgs(query="тест kubernetes")
    assert args.query == "тест kubernetes"
    assert args.limit == 10


def test_runet_discover_args_model_custom_limit() -> None:
    args = RunetDiscoverToolArgs(query="habr nginx", limit=20)
    assert args.limit == 20


def test_runet_discover_args_model_max_limit() -> None:
    args = RunetDiscoverToolArgs(query="query", limit=50)
    assert args.limit == 50


def test_runet_discover_args_model_rejects_empty_query() -> None:
    with pytest.raises(Exception):
        _ = RunetDiscoverToolArgs(query="")


def test_runet_discover_args_model_rejects_oversized_limit() -> None:
    with pytest.raises(Exception):
        _ = RunetDiscoverToolArgs(query="q", limit=51)


def test_runet_discover_tool_metadata() -> None:
    import apps.flows.tools.index_search as tool_module
    from apps.flows.src.tools.decorator import FunctionTool

    raw = tool_module.__dict__["runet_discover"]
    assert isinstance(raw, FunctionTool)
    assert raw.name == "runet_discover"
    assert "discovery" in raw.tags
    assert "runet" in raw.tags
    description_lower = raw.description.lower()
    assert "no live web fetch" in description_lower or "index-only" in description_lower


@pytest.mark.asyncio
async def test_runet_discover_returns_discovery_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.search.models import MetaSearchProviderStatus, MetaSearchResponse, WebSearchResult

    mock_result = WebSearchResult(
        title="Деплой Kubernetes на Habr",
        url="https://habr.com/ru/articles/1",
        snippet="Деплой Kubernetes — section_title",
        provider="index",
        provider_rank=1,
        score=0.92,
        doc_type="vector_pointer",
        section_title="Деплой Kubernetes",
        salient_terms=["ingress", "nginx"],
        heading_trail=["Habr", "DevOps"],
        canonical_url="https://habr.com/ru/articles/1",
    )
    mock_response = MetaSearchResponse(
        query="kubernetes деплой",
        results=[mock_result],
        providers={"index": MetaSearchProviderStatus(ok=True, results_count=1, latency_ms=50)},
    )

    mock_client = MagicMock()
    mock_client.search = AsyncMock(return_value=mock_response)

    import apps.flows.tools.index_search as tool_module

    monkeypatch.setattr(tool_module, "SearchClient", lambda: mock_client)

    result = await _runet_discover_impl(query="kubernetes деплой", limit=10)

    assert result["success"] is True
    assert result["is_discovery"] is True
    assert result["depth"] == 0
    assert "response" in result
    payload = result["response"]
    assert isinstance(payload, dict)
    assert payload.get("query") == "kubernetes деплой"
    results_raw = payload.get("results")
    assert isinstance(results_raw, list)
    assert len(results_raw) == 1
    first = results_raw[0]
    assert isinstance(first, dict)
    assert first.get("url") == "https://habr.com/ru/articles/1"
    assert first.get("doc_type") == "vector_pointer"
    assert first.get("section_title") == "Деплой Kubernetes"
    salient = first.get("salient_terms")
    assert isinstance(salient, list)
    assert "ingress" in salient


@pytest.mark.asyncio
async def test_runet_discover_calls_index_with_quick_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.search.models import MetaSearchProviderStatus, MetaSearchRequest, MetaSearchResponse

    mock_response = MetaSearchResponse(
        query="test",
        results=[],
        providers={"index": MetaSearchProviderStatus(ok=False, error="index returned no results")},
    )
    captured: list[MetaSearchRequest] = []

    async def capture_search(request: MetaSearchRequest) -> MetaSearchResponse:
        captured.append(request)
        return mock_response

    mock_client = MagicMock()
    mock_client.search = capture_search

    import apps.flows.tools.index_search as tool_module

    monkeypatch.setattr(tool_module, "SearchClient", lambda: mock_client)

    _ = await _runet_discover_impl(query="test", limit=5)

    assert len(captured) == 1
    req = captured[0]
    assert req.mode == "quick"
    assert "index" in req.providers
    assert "runet" in req.index_ids


@pytest.mark.asyncio
async def test_runet_discover_returns_error_on_client_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.clients.service_client import ServiceClientError

    mock_client = MagicMock()
    mock_client.search = AsyncMock(side_effect=ServiceClientError("connection refused"))

    import apps.flows.tools.index_search as tool_module

    monkeypatch.setattr(tool_module, "SearchClient", lambda: mock_client)

    result = await _runet_discover_impl(query="failing query")

    assert result["success"] is False
    assert "connection refused" in str(result.get("error", ""))
