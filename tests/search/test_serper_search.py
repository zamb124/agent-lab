import asyncio

import pytest
from fastapi import FastAPI, Request, Response
from granian.constants import Interfaces
from granian.server.embed import Server as GranianEmbedServer

from apps.search.config import (
    SearchIntegrationConfig,
    SearchLinkupConfig,
    SearchSerperConfig,
    SearchTavilyConfig,
    SearchTinyFishConfig,
)
from apps.search.providers.linkup import LinkupSearchProvider, parse_linkup_results
from apps.search.providers.serper import SerperSearchProvider, parse_serper_results
from apps.search.providers.tavily import TavilySearchProvider, parse_tavily_results
from apps.search.providers.tinyfish import TinyFishSearchProvider, parse_tinyfish_results
from core.search import MetaSearchRequest


@pytest.fixture
async def serper_stub_url(unused_tcp_port_factory):
    port = unused_tcp_port_factory()
    app = FastAPI()
    app.state.requests = []
    app.state.status_code = 200
    app.state.payload = {
        "organic": [
            {
                "title": "Humanitec A",
                "link": "https://example.com/search/?utm_source=test#frag",
                "position": 1,
            },
            {
                "title": "Humanitec B",
                "link": "https://EXAMPLE.com/search",
                "snippet": "Second result supplies snippet",
                "position": 2,
            },
        ]
    }

    @app.post("/search")
    async def search(request: Request):
        app.state.requests.append(
            {
                "headers": dict(request.headers),
                "json": await request.json(),
            }
        )
        if app.state.status_code >= 400:
            return Response("serper failed", status_code=app.state.status_code)
        return app.state.payload

    server = GranianEmbedServer(app, interface=Interfaces.ASGI, address="127.0.0.1", port=port)
    task = asyncio.create_task(server.serve())
    try:
        await _wait_tcp_ready("127.0.0.1", port)
        yield f"http://127.0.0.1:{port}", app.state
    finally:
        server.stop()
        await task


async def _wait_tcp_ready(host: str, port: int, attempts: int = 100) -> None:
    for _ in range(attempts):
        try:
            reader, writer = await asyncio.open_connection(host, port)
            writer.close()
            await writer.wait_closed()
            return
        except OSError:
            await asyncio.sleep(0.05)
    raise RuntimeError(f"granian embed server не поднял порт {host}:{port}")


@pytest.fixture
async def provider_stub_url(unused_tcp_port_factory):
    port = unused_tcp_port_factory()
    app = FastAPI()
    app.state.requests = []
    app.state.fail_tinyfish = False
    app.state.fail_linkup = False
    app.state.fail_tavily = False
    app.state.invalid_tinyfish_json = False
    app.state.invalid_linkup_json = False
    app.state.invalid_tavily_json = False

    @app.get("/tinyfish")
    async def tinyfish(request: Request):
        app.state.requests.append(
            {
                "path": "/tinyfish",
                "headers": dict(request.headers),
                "query": dict(request.query_params),
            }
        )
        if app.state.fail_tinyfish:
            return Response("tinyfish failed", status_code=503)
        if app.state.invalid_tinyfish_json:
            return Response("not-json", media_type="text/plain")
        return {
            "results": [
                {
                    "title": "TinyFish A",
                    "url": "https://tiny.example/a?utm_source=test",
                    "snippet": "Tiny snippet",
                    "position": 1,
                    "site_name": "tiny.example",
                }
            ]
        }

    @app.post("/search")
    async def tavily(request: Request):
        app.state.requests.append(
            {
                "path": "/search",
                "headers": dict(request.headers),
                "json": await request.json(),
            }
        )
        if app.state.fail_tavily:
            return Response("tavily failed", status_code=503)
        if app.state.invalid_tavily_json:
            return Response("not-json", media_type="text/plain")
        return {
            "query": "Humanitec",
            "results": [
                {
                    "title": "Tavily A",
                    "url": "https://tavily.example/a",
                    "content": "Tavily snippet",
                    "score": 0.91,
                    "published_date": "2026-05-01",
                }
            ],
        }

    @app.post("/v1/search")
    async def linkup(request: Request):
        app.state.requests.append(
            {
                "path": "/v1/search",
                "headers": dict(request.headers),
                "json": await request.json(),
            }
        )
        if app.state.fail_linkup:
            return Response("linkup failed", status_code=503)
        if app.state.invalid_linkup_json:
            return Response("not-json", media_type="text/plain")
        return {
            "results": [
                {
                    "name": "Linkup A",
                    "url": "https://linkup.example/a",
                    "content": "Linkup snippet",
                    "type": "source",
                }
            ]
        }

    server = GranianEmbedServer(app, interface=Interfaces.ASGI, address="127.0.0.1", port=port)
    task = asyncio.create_task(server.serve())
    try:
        await _wait_tcp_ready("127.0.0.1", port)
        yield f"http://127.0.0.1:{port}", app.state
    finally:
        server.stop()
        await task


def test_parse_serper_results_normalizes_organic_items() -> None:
    payload = {
        "organic": [
            {
                "title": "Humanitec",
                "link": "https://humanitec.ru/?utm_source=test#frag",
                "snippet": "AI platform",
                "position": 1,
                "date": "May 1, 2026",
            },
            {
                "title": "",
                "link": "https://example.com",
                "snippet": "Skipped",
                "position": 2,
            },
        ]
    }

    results = parse_serper_results(payload, limit=10)

    assert len(results) == 1
    assert results[0].title == "Humanitec"
    assert results[0].url == "https://humanitec.ru/?utm_source=test#frag"
    assert results[0].display_url == "humanitec.ru"
    assert results[0].provider == "serper"
    assert results[0].provider_rank == 1
    assert results[0].published_at == "May 1, 2026"


def test_parse_serper_results_applies_limit() -> None:
    payload = {
        "organic": [
            {"title": "A", "link": "https://a.example", "position": 1},
            {"title": "B", "link": "https://b.example", "position": 2},
        ]
    }

    results = parse_serper_results(payload, limit=1)

    assert [item.title for item in results] == ["A"]


def test_parse_serper_results_handles_non_standard_payloads() -> None:
    assert parse_serper_results(None, limit=10) == []
    assert parse_serper_results({"organic": None}, limit=10) == []

    payload = {
        "organic": [
            "skip",
            {
                "title": "Long path",
                "link": "https://example.com/" + ("a" * 80),
                "position": "not-int",
            },
            {
                "title": "Bad URL",
                "link": "http://[",
                "position": 4,
            },
        ]
    }
    results = parse_serper_results(payload, limit=10)

    assert results[0].provider_rank == 2
    assert results[0].display_url.endswith("...")
    assert results[1].display_url == "http://["


def test_parse_tinyfish_results_normalizes_items() -> None:
    payload = {
        "results": [
            "skip",
            {
                "title": "Tiny",
                "url": "https://tiny.example/path",
                "snippet": "Body",
                "position": 3,
                "site_name": "Tiny Site",
            },
            {
                "title": "Tiny 2",
                "url": "https://tiny.example/path-2",
                "snippet": "Body 2",
            },
            {"title": "", "url": "https://skip.example"},
        ]
    }

    results = parse_tinyfish_results(payload, limit=1)

    assert len(results) == 1
    assert results[0].title == "Tiny"
    assert results[0].display_url == "Tiny Site"
    assert results[0].provider == "tinyfish"
    assert results[0].provider_rank == 3
    assert parse_tinyfish_results(None, limit=10) == []
    assert parse_tinyfish_results({"results": None}, limit=10) == []
    assert parse_tinyfish_results({"results": [{"title": "", "url": "https://skip.example"}]}, limit=10) == []


def test_parse_linkup_results_normalizes_items() -> None:
    payload = {
        "results": [
            "skip",
            {
                "name": "Linkup",
                "url": "https://linkup.example/path",
                "content": "Body",
                "type": "source",
            },
            {
                "name": "Linkup 2",
                "url": "https://linkup.example/path-2",
                "content": "Body 2",
            },
            {"name": "Skip", "url": ""},
        ]
    }

    results = parse_linkup_results(payload, limit=1)

    assert len(results) == 1
    assert results[0].title == "Linkup"
    assert results[0].display_url == "linkup.example/path"
    assert results[0].provider == "linkup"
    assert results[0].source_type == "source"
    assert parse_linkup_results(None, limit=10) == []
    assert parse_linkup_results({"results": None}, limit=10) == []
    assert parse_linkup_results({"results": [{"name": "Skip", "url": ""}]}, limit=10) == []


def test_parse_tavily_results_normalizes_items() -> None:
    payload = {
        "results": [
            "skip",
            {
                "title": "Tavily",
                "url": "https://tavily.example/path",
                "content": "Body",
                "score": 0.85,
                "published_date": "2026-05-01",
            },
            {
                "title": "Tavily 2",
                "url": "https://tavily.example/path-2",
                "content": "Body 2",
                "score": -1,
            },
            {"title": "Skip", "url": ""},
        ]
    }

    results = parse_tavily_results(payload, limit=10)

    assert len(results) == 2
    assert results[0].title == "Tavily"
    assert results[0].display_url == "tavily.example/path"
    assert results[0].provider == "tavily"
    assert results[0].score == 0.85
    assert results[0].published_at == "2026-05-01"
    assert results[1].score == 0.0
    assert len(parse_tavily_results(payload, limit=1)) == 1
    assert parse_tavily_results(None, limit=10) == []
    assert parse_tavily_results({"results": None}, limit=10) == []
    assert parse_tavily_results({"results": [{"title": "Skip", "url": ""}]}, limit=10) == []


@pytest.mark.asyncio
async def test_serper_provider_calls_http_endpoint_and_normalizes_results(serper_stub_url) -> None:
    base_url, state = serper_stub_url
    provider = SerperSearchProvider(
        SearchSerperConfig(api_key="test-key", base_url=base_url, timeout_seconds=3)
    )

    results, status = await provider.search(
        MetaSearchRequest(
            query="Humanitec",
            limit=2,
            language="RU",
            region="RU",
        )
    )

    assert status.ok is True
    assert status.results_count == 2
    assert [item.title for item in results] == ["Humanitec A", "Humanitec B"]
    assert state.requests[0]["headers"]["x-api-key"] == "test-key"
    assert state.requests[0]["json"] == {
        "q": "Humanitec",
        "num": 2,
        "gl": "ru",
        "hl": "ru",
        "autocorrect": True,
    }


@pytest.mark.asyncio
async def test_serper_provider_reports_disabled_and_http_errors(serper_stub_url) -> None:
    disabled = SerperSearchProvider(SearchSerperConfig(enabled=False))
    _, disabled_status = await disabled.search(MetaSearchRequest(query="Humanitec"))
    assert disabled_status.ok is False
    assert disabled_status.error == "serper provider is disabled"

    base_url, state = serper_stub_url
    state.status_code = 503
    provider = SerperSearchProvider(
        SearchSerperConfig(api_key="test-key", base_url=base_url, timeout_seconds=3)
    )
    _, status = await provider.search(MetaSearchRequest(query="Humanitec"))

    assert status.ok is False
    assert "serper returned HTTP 503" in str(status.error)


@pytest.mark.asyncio
async def test_serper_provider_reports_invalid_json_response(serper_stub_url) -> None:
    base_url, state = serper_stub_url
    state.payload = Response("not-json", media_type="text/plain")
    provider = SerperSearchProvider(
        SearchSerperConfig(api_key="test-key", base_url=base_url, timeout_seconds=3)
    )

    _, status = await provider.search(MetaSearchRequest(query="Humanitec"))

    assert status.ok is False
    assert status.error


@pytest.mark.asyncio
async def test_tinyfish_provider_calls_http_endpoint_and_normalizes_results(provider_stub_url) -> None:
    base_url, state = provider_stub_url
    provider = TinyFishSearchProvider(
        SearchTinyFishConfig(api_key="tiny-key", base_url=f"{base_url}/tinyfish")
    )

    results, status = await provider.search(
        MetaSearchRequest(query="Humanitec", limit=2, language="RU", region="RU")
    )

    assert status.ok is True
    assert status.results_count == 1
    assert results[0].title == "TinyFish A"
    assert state.requests[0]["headers"]["x-api-key"] == "tiny-key"
    assert state.requests[0]["query"] == {
        "query": "Humanitec",
        "location": "RU",
        "language": "ru",
    }


@pytest.mark.asyncio
async def test_tinyfish_provider_reports_disabled_missing_key_and_http_errors(
    provider_stub_url,
) -> None:
    disabled = TinyFishSearchProvider(SearchTinyFishConfig(enabled=False))
    _, disabled_status = await disabled.search(MetaSearchRequest(query="Humanitec"))
    assert disabled_status.ok is False
    assert disabled_status.error == "tinyfish provider is disabled"

    missing = TinyFishSearchProvider(SearchTinyFishConfig())
    _, missing_status = await missing.search(MetaSearchRequest(query="Humanitec"))
    assert missing_status.ok is False
    assert missing_status.error == "tinyfish api key is not configured"

    base_url, state = provider_stub_url
    state.fail_tinyfish = True
    provider = TinyFishSearchProvider(
        SearchTinyFishConfig(api_key="tiny-key", base_url=f"{base_url}/tinyfish")
    )
    _, status = await provider.search(MetaSearchRequest(query="Humanitec"))
    assert status.ok is False
    assert "tinyfish returned HTTP 503" in str(status.error)

    state.fail_tinyfish = False
    state.invalid_tinyfish_json = True
    _, invalid_status = await provider.search(MetaSearchRequest(query="Humanitec"))
    assert invalid_status.ok is False
    assert invalid_status.error


@pytest.mark.asyncio
async def test_linkup_provider_calls_http_endpoint_and_normalizes_results(provider_stub_url) -> None:
    base_url, state = provider_stub_url
    provider = LinkupSearchProvider(
        SearchLinkupConfig(api_key="linkup-key", base_url=base_url, depth="fast")
    )

    results, status = await provider.search(MetaSearchRequest(query="Humanitec", limit=2))

    assert status.ok is True
    assert status.results_count == 1
    assert results[0].title == "Linkup A"
    assert state.requests[0]["headers"]["authorization"] == "Bearer linkup-key"
    assert state.requests[0]["json"] == {
        "q": "Humanitec",
        "depth": "fast",
        "outputType": "searchResults",
        "includeImages": False,
        "maxResults": 2,
    }


@pytest.mark.asyncio
async def test_linkup_provider_reports_disabled_missing_key_and_http_errors(
    provider_stub_url,
) -> None:
    disabled = LinkupSearchProvider(SearchLinkupConfig(enabled=False))
    _, disabled_status = await disabled.search(MetaSearchRequest(query="Humanitec"))
    assert disabled_status.ok is False
    assert disabled_status.error == "linkup provider is disabled"

    missing = LinkupSearchProvider(SearchLinkupConfig())
    _, missing_status = await missing.search(MetaSearchRequest(query="Humanitec"))
    assert missing_status.ok is False
    assert missing_status.error == "linkup api key is not configured"

    base_url, state = provider_stub_url
    state.fail_linkup = True
    provider = LinkupSearchProvider(SearchLinkupConfig(api_key="linkup-key", base_url=base_url))
    _, status = await provider.search(MetaSearchRequest(query="Humanitec"))
    assert status.ok is False
    assert "linkup returned HTTP 503" in str(status.error)

    state.fail_linkup = False
    state.invalid_linkup_json = True
    _, invalid_status = await provider.search(MetaSearchRequest(query="Humanitec"))
    assert invalid_status.ok is False
    assert invalid_status.error


@pytest.mark.asyncio
async def test_tavily_provider_calls_http_endpoint_and_normalizes_results(provider_stub_url) -> None:
    base_url, state = provider_stub_url
    provider = TavilySearchProvider(
        SearchTavilyConfig(api_key="tavily-key", base_url=base_url, search_depth="advanced")
    )

    results, status = await provider.search(MetaSearchRequest(query="Humanitec", limit=2))

    assert status.ok is True
    assert status.results_count == 1
    assert results[0].title == "Tavily A"
    assert state.requests[0]["headers"]["authorization"] == "Bearer tavily-key"
    assert state.requests[0]["json"] == {
        "query": "Humanitec",
        "max_results": 2,
        "search_depth": "advanced",
        "topic": "general",
        "include_answer": False,
        "include_images": False,
        "include_raw_content": False,
    }


@pytest.mark.asyncio
async def test_tavily_provider_reports_disabled_missing_key_and_http_errors(
    provider_stub_url,
) -> None:
    disabled = TavilySearchProvider(SearchTavilyConfig(enabled=False))
    _, disabled_status = await disabled.search(MetaSearchRequest(query="Humanitec"))
    assert disabled_status.ok is False
    assert disabled_status.error == "tavily provider is disabled"

    missing = TavilySearchProvider(SearchTavilyConfig())
    _, missing_status = await missing.search(MetaSearchRequest(query="Humanitec"))
    assert missing_status.ok is False
    assert missing_status.error == "tavily api key is not configured"

    base_url, state = provider_stub_url
    state.fail_tavily = True
    provider = TavilySearchProvider(SearchTavilyConfig(api_key="tavily-key", base_url=base_url))
    _, status = await provider.search(MetaSearchRequest(query="Humanitec"))
    assert status.ok is False
    assert "tavily returned HTTP 503" in str(status.error)

    state.fail_tavily = False
    state.invalid_tavily_json = True
    _, invalid_status = await provider.search(MetaSearchRequest(query="Humanitec"))
    assert invalid_status.ok is False
    assert invalid_status.error


@pytest.mark.asyncio
async def test_meta_search_ranks_dedupes_and_reports_unsupported_providers(
    serper_stub_url,
    provider_state_store,
    meta_search_service_builder,
) -> None:
    base_url, _ = serper_stub_url
    service = meta_search_service_builder(
        SearchIntegrationConfig(
            serper=SearchSerperConfig(api_key="test-key", base_url=base_url, timeout_seconds=3)
        ),
        provider_state_store,
    )

    response = await service.search(
        MetaSearchRequest(
            query="Humanitec",
            providers=["google", "unsupported"],
            provider_strategy="merge",
            limit=10,
        )
    )

    assert response.providers["serper"].ok is True
    assert response.providers["unsupported"].ok is False
    assert response.results[0].rank == 1
    assert response.results[0].title == "Humanitec B"
    assert response.results[0].snippet == "Second result supplies snippet"
    assert response.results[0].score > 0


@pytest.mark.asyncio
async def test_meta_search_keeps_unparseable_urls(
    serper_stub_url,
    provider_state_store,
    meta_search_service_builder,
) -> None:
    base_url, state = serper_stub_url
    state.payload = {
        "organic": [
            {
                "title": "Bad URL",
                "link": "http://[",
                "position": 1,
            }
        ]
    }
    service = meta_search_service_builder(
        SearchIntegrationConfig(
            serper=SearchSerperConfig(api_key="test-key", base_url=base_url, timeout_seconds=3)
        ),
        provider_state_store,
    )

    response = await service.search(MetaSearchRequest(query="Humanitec"))

    assert response.results[0].url == "http://["


@pytest.mark.asyncio
async def test_meta_search_first_available_uses_redis_state_and_next_provider(
    provider_stub_url,
    provider_state_store,
    meta_search_service_builder,
) -> None:
    base_url, _ = provider_stub_url
    await provider_state_store.mark_unavailable("tinyfish", "rate limited")
    service = meta_search_service_builder(
        SearchIntegrationConfig(
            provider_order=["tinyfish", "linkup", "serper"],
            tinyfish=SearchTinyFishConfig(api_key="tiny-key", base_url=f"{base_url}/tinyfish"),
            linkup=SearchLinkupConfig(api_key="linkup-key", base_url=base_url),
        ),
        provider_state_store,
    )

    response = await service.search(MetaSearchRequest(query="Humanitec", providers=["auto"]))

    assert response.providers["tinyfish"].skipped is True
    assert response.providers["tinyfish"].skip_reason == "provider marked unavailable in redis"
    assert response.providers["linkup"].selected is True
    assert response.results[0].provider == "linkup"


@pytest.mark.asyncio
async def test_meta_search_merge_skips_redis_unavailable_provider(
    provider_stub_url,
    provider_state_store,
    meta_search_service_builder,
) -> None:
    base_url, _ = provider_stub_url
    await provider_state_store.mark_unavailable("tinyfish", "rate limited")
    service = meta_search_service_builder(
        SearchIntegrationConfig(
            provider_order=["tinyfish", "linkup"],
            tinyfish=SearchTinyFishConfig(api_key="tiny-key", base_url=f"{base_url}/tinyfish"),
            linkup=SearchLinkupConfig(api_key="linkup-key", base_url=base_url),
        ),
        provider_state_store,
    )

    response = await service.search(
        MetaSearchRequest(
            query="Humanitec",
            providers=["auto"],
            provider_strategy="merge",
        )
    )

    assert response.providers["tinyfish"].skipped is True
    assert response.providers["linkup"].selected is True
    assert response.results[0].provider == "linkup"


@pytest.mark.asyncio
async def test_meta_search_auto_appends_explicit_provider_after_default_order(
    provider_stub_url,
    provider_state_store,
    meta_search_service_builder,
) -> None:
    base_url, _ = provider_stub_url
    service = meta_search_service_builder(
        SearchIntegrationConfig(
            provider_order=["linkup"],
            linkup=SearchLinkupConfig(api_key="linkup-key", base_url=base_url),
        ),
        provider_state_store,
    )

    response = await service.search(
        MetaSearchRequest(query="Humanitec", providers=["auto", "unsupported"])
    )

    assert response.providers["linkup"].ok is True
    assert "unsupported" not in response.providers


@pytest.mark.asyncio
async def test_meta_search_resolves_tavily_aliases(
    provider_stub_url,
    provider_state_store,
    meta_search_service_builder,
) -> None:
    base_url, _ = provider_stub_url
    service = meta_search_service_builder(
        SearchIntegrationConfig(
            tavily=SearchTavilyConfig(api_key="tavily-key", base_url=base_url),
        ),
        provider_state_store,
    )

    response = await service.search(MetaSearchRequest(query="Humanitec", providers=["travily"]))

    assert response.providers["tavily"].ok is True
    assert response.results[0].provider == "tavily"


@pytest.mark.asyncio
async def test_meta_search_marks_failed_provider_unavailable_and_continues(
    provider_stub_url,
    provider_state_store,
    meta_search_service_builder,
) -> None:
    base_url, state = provider_stub_url
    state.fail_tinyfish = True
    service = meta_search_service_builder(
        SearchIntegrationConfig(
            provider_order=["tinyfish", "linkup"],
            tinyfish=SearchTinyFishConfig(api_key="tiny-key", base_url=f"{base_url}/tinyfish"),
            linkup=SearchLinkupConfig(api_key="linkup-key", base_url=base_url),
        ),
        provider_state_store,
    )

    response = await service.search(MetaSearchRequest(query="Humanitec", providers=["auto"]))
    record = await provider_state_store.get("tinyfish")

    assert response.providers["tinyfish"].ok is False
    assert response.providers["tinyfish"].selected is True
    assert response.providers["linkup"].ok is True
    assert record is not None
    assert record.available is False
    assert record.consecutive_failures == 1


@pytest.mark.asyncio
async def test_meta_search_merge_combines_available_providers(
    provider_stub_url,
    serper_stub_url,
    provider_state_store,
    meta_search_service_builder,
) -> None:
    provider_base_url, _ = provider_stub_url
    serper_base_url, _ = serper_stub_url
    service = meta_search_service_builder(
        SearchIntegrationConfig(
            provider_order=["tinyfish", "serper"],
            tinyfish=SearchTinyFishConfig(
                api_key="tiny-key",
                base_url=f"{provider_base_url}/tinyfish",
            ),
            serper=SearchSerperConfig(
                api_key="serper-key",
                base_url=serper_base_url,
                timeout_seconds=3,
            ),
        ),
        provider_state_store,
    )

    response = await service.search(
        MetaSearchRequest(
            query="Humanitec",
            providers=["auto"],
            provider_strategy="merge",
        )
    )

    assert response.providers["tinyfish"].selected is True
    assert response.providers["serper"].selected is True
    assert {item.provider for item in response.results} == {"tinyfish", "serper"}


@pytest.mark.asyncio
async def test_meta_search_merge_marks_failed_provider_unavailable(
    provider_stub_url,
    provider_state_store,
    meta_search_service_builder,
) -> None:
    base_url, state = provider_stub_url
    state.fail_tinyfish = True
    service = meta_search_service_builder(
        SearchIntegrationConfig(
            provider_order=["tinyfish", "linkup"],
            tinyfish=SearchTinyFishConfig(api_key="tiny-key", base_url=f"{base_url}/tinyfish"),
            linkup=SearchLinkupConfig(api_key="linkup-key", base_url=base_url),
        ),
        provider_state_store,
    )

    response = await service.search(
        MetaSearchRequest(
            query="Humanitec",
            providers=["auto"],
            provider_strategy="merge",
        )
    )

    record = await provider_state_store.get("tinyfish")
    assert response.providers["tinyfish"].selected is True
    assert response.providers["tinyfish"].ok is False
    assert response.providers["linkup"].ok is True
    assert record is not None
    assert record.available is False
