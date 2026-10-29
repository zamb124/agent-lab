"""Live Centrifugo RPC + REST identity для всех SEARCH_OPERATIONS.

Hop как у SPA: SESSION JWT → Centrifugo :19000 `platform.event` → bus :9025
→ `POST /search/api/internal/realtime/command` → тот же `op_*`.
REST — Granian search :9010; индекс для meta-поиска наполняется через RAG :9002.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

import pytest
from httpx2 import AsyncClient, Response

from apps.search.realtime.command_router import SEARCH_OPERATIONS
from core.types import JsonObject, JsonValue, require_json_object
from core.utils.tokens import get_token_service
from tests.realtime.centrifugo_ws import connect_centrifugo, rpc_platform_event

_API = "/search/api/v1"
_PATH_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")
_TRANSPORT_MARKER = re.compile(r"[-_ ](?:ws|rest)(?=$|[^a-z0-9])")
_REQUEST_SCOPE_IN_ERROR = re.compile(
    r',?\s*"(?:request_id|trace_id|service)":\s*"(?:[^"\\]|\\.)*"'
    r'|,\s*"observability":\s*\{[^{}]*\}'
)
# Оркестратор crawl подхватывает домены/URL фоном между WS- и REST-вызовом: статусы и метки времени волатильны.
_VOLATILE_KEYS = frozenset(
    {
        "crawl_job_id",
        "crawl_domain_id",
        "crawl_url_id",
        "created_at",
        "updated_at",
        "next_crawl_after",
        "last_discovered_at",
        "last_crawled_at",
        "last_error",
        "crawl_status",
        "fetch_transport",
        "fetch_attempts",
        "next_retry_after",
        "content_hash",
        "extract_content_hash",
        "document_id",
        "extract_title",
        "extract_markdown",
        "indexed_content",
        "status",
        "domains_scheduled",
        "urls_discovered",
        "urls_fetched",
        "urls_indexed",
        "urls_skipped",
        "urls_enriched",
        "urls_enrichment_failed",
        "errors",
        "started_at",
        "finished_at",
        "serp_cache_key",
        "latency_ms",
        "request_id",
        "trace_id",
        "service",
        "observability",
    }
)

CompareMode = Literal["exact", "normalized"]
# body_profile_query: crawl_profile_id уходит query-параметром, остальное (минус path) — тело.
PayloadStrategy = Literal["body_minus_path", "body_profile_query", "query", "none"]
SetupFn = Callable[["LiveCtx"], Awaitable[JsonObject]]


@dataclass(frozen=True)
class RestMirror:
    method: str
    url: str
    strategy: PayloadStrategy


@dataclass(frozen=True)
class OpCase:
    rest: RestMirror
    setup: SetupFn
    same_resource: bool
    compare: CompareMode


@dataclass
class LiveCtx:
    client: AsyncClient
    rag_client: AsyncClient
    headers: dict[str, str]
    unique_id: str
    suffix: str


def _json(response: Response, label: str) -> JsonObject:
    return require_json_object(response.json(), label)


def _str_field(payload: JsonObject, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise AssertionError(f"{key} is required, got {value!r}")
    return value


def _normalize(value: JsonValue | None) -> JsonValue | None:
    if isinstance(value, dict):
        normalized: dict[str, JsonValue | None] = {}
        for key, item in value.items():
            if key in _VOLATILE_KEYS:
                continue
            normalized_item = _normalize(item)
            if key == "error" and isinstance(normalized_item, str):
                normalized_item = _REQUEST_SCOPE_IN_ERROR.sub("", normalized_item)
            normalized[key] = normalized_item
        return normalized
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, str):
        return _TRANSPORT_MARKER.sub("", value)
    return value


def _event_payload(event: JsonObject) -> JsonObject:
    raw = event.get("payload")
    if raw is None:
        return {}
    return require_json_object(raw, "event.payload")


async def _expect_json(response: Response, *, ok: tuple[int, ...], label: str) -> JsonObject:
    assert response.status_code in ok, f"{label} {response.status_code}: {response.text}"
    if response.status_code == 204:
        return {}
    return _json(response, label)


def _slug(ctx: LiveCtx, kind: str) -> str:
    return f"idx_{kind}_{ctx.unique_id}_{ctx.suffix}".lower().replace("-", "_")[:63]


async def _create_index(ctx: LiveCtx, kind: str) -> str:
    search_index_id = _slug(ctx, kind)
    response = await ctx.client.post(
        f"{_API}/search-indexes",
        headers=ctx.headers,
        json={
            "search_index_id": search_index_id,
            "display_name": f"Live {kind} {ctx.suffix}",
            "rag_namespace_id": f"{search_index_id}:ns",
            "rag_collection_id": search_index_id,
        },
    )
    body = await _expect_json(response, ok=(201,), label="create_index")
    return _str_field(body, "search_index_id")


async def _create_profile(ctx: LiveCtx, kind: str) -> str:
    search_index_id = await _create_index(ctx, kind)
    crawl_profile_id = f"cr_{search_index_id}"[:64]
    response = await ctx.client.post(
        f"{_API}/crawl/profiles",
        headers=ctx.headers,
        json={
            "crawl_profile_id": crawl_profile_id,
            "search_index_id": search_index_id,
            "seed_source": "manual",
            "browser_fallback_enabled": False,
        },
    )
    body = await _expect_json(response, ok=(201,), label="create_profile")
    return _str_field(require_json_object(body["profile"], "profile"), "crawl_profile_id")


async def _create_domain(ctx: LiveCtx, crawl_profile_id: str, kind: str) -> JsonObject:
    response = await ctx.client.post(
        f"{_API}/crawl/profiles/{crawl_profile_id}/domains",
        headers=ctx.headers,
        json={"domain": f"{kind}-{ctx.unique_id}-{ctx.suffix}.example.com".lower(), "category": "manual"},
    )
    return await _expect_json(response, ok=(201,), label="create_domain")


async def _add_url(ctx: LiveCtx, crawl_profile_id: str, crawl_domain_id: str, kind: str) -> str:
    response = await ctx.client.post(
        f"{_API}/crawl/domains/{crawl_domain_id}/urls",
        headers=ctx.headers,
        params={"crawl_profile_id": crawl_profile_id},
        json={"urls": [f"https://{kind}-{ctx.unique_id}-{ctx.suffix}.example.com/page".lower()]},
    )
    _ = await _expect_json(response, ok=(202,), label="add_url")
    listing = await ctx.client.get(
        f"{_API}/crawl/urls",
        headers=ctx.headers,
        params={"crawl_profile_id": crawl_profile_id, "limit": 10, "offset": 0},
    )
    body = await _expect_json(listing, ok=(200,), label="list_urls")
    items = body.get("items")
    if not isinstance(items, list) or not items:
        raise AssertionError("crawl url list is empty after add")
    first = require_json_object(items[0], "crawl_url")
    return _str_field(first, "crawl_url_id")


async def _indexed_search_pool(ctx: LiveCtx, kind: str) -> tuple[str, str, str]:
    """Индекс + документ в RAG, затем поиск до появления результатов: (query, serp_cache_key, search_index_id)."""
    search_index_id = await _create_index(ctx, kind)
    marker = f"live_search_marker_{ctx.unique_id}_{ctx.suffix}"
    text = f"Документ платформенного индекса содержит уникальный маркер {marker} и длинный текст для chunking."
    ingest = await ctx.rag_client.post(
        f"/rag/api/v1/namespaces/{search_index_id}:ns/ingest-text",
        headers=ctx.headers,
        json={
            "text": text,
            "document_name": f"live-{kind}-{ctx.suffix}.md",
            "metadata": {"source_url": f"https://live.test/{ctx.unique_id}/{kind}", "collection_id": search_index_id},
        },
    )
    _ = await _expect_json(ingest, ok=(200,), label="rag_ingest")
    deadline = asyncio.get_running_loop().time() + 40.0
    while asyncio.get_running_loop().time() < deadline:
        response = await ctx.client.post(
            f"{_API}/search",
            headers=ctx.headers,
            json={"query": text, "limit": 5, "providers": ["index"], "index_ids": [search_index_id]},
        )
        body = await _expect_json(response, ok=(200,), label="index_search")
        cache_key = body.get("serp_cache_key")
        if body.get("results") and isinstance(cache_key, str) and cache_key:
            return text, cache_key, search_index_id
        await asyncio.sleep(1.0)
    raise AssertionError(f"index search returned no results for {search_index_id}")


async def _setup_profiles_list(ctx: LiveCtx) -> JsonObject:
    _ = await _create_profile(ctx, "plist")
    return {"limit": 200, "offset": 0}


async def _setup_profiles_create(ctx: LiveCtx) -> JsonObject:
    search_index_id = await _create_index(ctx, "pcreate")
    return {
        "crawl_profile_id": f"cr_{search_index_id}"[:64],
        "search_index_id": search_index_id,
        "seed_source": "manual",
        "browser_fallback_enabled": False,
    }


async def _setup_profiles_update(ctx: LiveCtx) -> JsonObject:
    crawl_profile_id = await _create_profile(ctx, "pupd")
    return {"crawl_profile_id": crawl_profile_id, "max_domains_per_tick": 3, "denylist_domains": ["spam.example"]}


async def _setup_profiles_summary(ctx: LiveCtx) -> JsonObject:
    return {"crawl_profile_id": await _create_profile(ctx, "psum")}


async def _setup_profiles_tranco_seed(ctx: LiveCtx) -> JsonObject:
    return {"crawl_profile_id": await _create_profile(ctx, "ptranco"), "tranco_limit": 5}


async def _setup_jobs_queue(ctx: LiveCtx) -> JsonObject:
    return {"crawl_profile_id": await _create_profile(ctx, "jqueue"), "trigger": "manual"}


async def _setup_jobs_list(ctx: LiveCtx) -> JsonObject:
    return {"crawl_profile_id": await _create_profile(ctx, "jlist"), "limit": 50, "offset": 0}


async def _setup_jobs_get(ctx: LiveCtx) -> JsonObject:
    crawl_profile_id = await _create_profile(ctx, "jget")
    domain = await _create_domain(ctx, crawl_profile_id, "jget")
    run = await ctx.client.post(
        f"{_API}/crawl/domains/{_str_field(domain, 'crawl_domain_id')}/run",
        headers=ctx.headers,
        params={"crawl_profile_id": crawl_profile_id},
    )
    body = await _expect_json(run, ok=(202,), label="run_domain")
    return {"crawl_job_id": _str_field(body, "crawl_job_id")}


async def _setup_domains_list(ctx: LiveCtx) -> JsonObject:
    crawl_profile_id = await _create_profile(ctx, "dlist")
    _ = await _create_domain(ctx, crawl_profile_id, "dlist")
    return {"crawl_profile_id": crawl_profile_id, "limit": 50, "offset": 0}


async def _setup_domains_create(ctx: LiveCtx) -> JsonObject:
    crawl_profile_id = await _create_profile(ctx, "dcreate")
    return {
        "crawl_profile_id": crawl_profile_id,
        "domain": f"dcreate-{ctx.unique_id}-{ctx.suffix}.example.com".lower(),
        "category": "manual",
    }


async def _domain_ref(ctx: LiveCtx, kind: str) -> JsonObject:
    crawl_profile_id = await _create_profile(ctx, kind)
    domain = await _create_domain(ctx, crawl_profile_id, kind)
    return {"crawl_profile_id": crawl_profile_id, "crawl_domain_id": _str_field(domain, "crawl_domain_id")}


async def _setup_domains_update(ctx: LiveCtx) -> JsonObject:
    ref = await _domain_ref(ctx, "dupd")
    return {**ref, "status": "paused", "refresh_interval_seconds": 7200}


async def _setup_domains_remove(ctx: LiveCtx) -> JsonObject:
    return await _domain_ref(ctx, "drm")


async def _setup_domains_run(ctx: LiveCtx) -> JsonObject:
    return await _domain_ref(ctx, "drun")


async def _setup_domains_urls_add(ctx: LiveCtx) -> JsonObject:
    ref = await _domain_ref(ctx, "durls")
    return {**ref, "urls": [f"https://durls-{ctx.unique_id}-{ctx.suffix}.example.com/a".lower()]}


async def _setup_urls_list(ctx: LiveCtx) -> JsonObject:
    ref = await _domain_ref(ctx, "ulist")
    _ = await _add_url(ctx, _str_field(ref, "crawl_profile_id"), _str_field(ref, "crawl_domain_id"), "ulist")
    return {"crawl_profile_id": _str_field(ref, "crawl_profile_id"), "limit": 50, "offset": 0}


async def _url_ref(ctx: LiveCtx, kind: str) -> JsonObject:
    ref = await _domain_ref(ctx, kind)
    crawl_url_id = await _add_url(ctx, _str_field(ref, "crawl_profile_id"), _str_field(ref, "crawl_domain_id"), kind)
    return {"crawl_profile_id": _str_field(ref, "crawl_profile_id"), "crawl_url_id": crawl_url_id}


async def _setup_urls_get(ctx: LiveCtx) -> JsonObject:
    return await _url_ref(ctx, "uget")


async def _setup_urls_recrawl(ctx: LiveCtx) -> JsonObject:
    return await _url_ref(ctx, "urecrawl")


async def _setup_seed_import(ctx: LiveCtx) -> JsonObject:
    return {"crawl_profile_id": await _create_profile(ctx, "seed"), "seed_source": "tranco", "tranco_limit": 5}


async def _setup_indexes_list(ctx: LiveCtx) -> JsonObject:
    _ = await _create_index(ctx, "ilist")
    return {"limit": 200, "offset": 0}


async def _setup_indexes_get(ctx: LiveCtx) -> JsonObject:
    return {"search_index_id": await _create_index(ctx, "iget")}


async def _setup_indexes_create(ctx: LiveCtx) -> JsonObject:
    search_index_id = _slug(ctx, "icreate")
    return {
        "search_index_id": search_index_id,
        "display_name": f"Live icreate {ctx.suffix}",
        "rag_namespace_id": f"{search_index_id}:ns",
        "rag_collection_id": search_index_id,
    }


async def _setup_indexes_update(ctx: LiveCtx) -> JsonObject:
    return {"search_index_id": await _create_index(ctx, "iupd"), "description": f"patched-{ctx.suffix}"}


async def _setup_indexes_batch_get(ctx: LiveCtx) -> JsonObject:
    return {"search_index_ids": [await _create_index(ctx, "ibatch")]}


async def _setup_query_search(ctx: LiveCtx) -> JsonObject:
    query, _, search_index_id = await _indexed_search_pool(ctx, "qsearch")
    return {"query": query, "limit": 5, "providers": ["index"], "index_ids": [search_index_id]}


async def _setup_query_serp_more(ctx: LiveCtx) -> JsonObject:
    _, cache_key, _ = await _indexed_search_pool(ctx, "qmore")
    return {"serp_cache_key": cache_key, "offset": 0, "limit": 5}


async def _setup_query_serp_refine(ctx: LiveCtx) -> JsonObject:
    query, cache_key, _ = await _indexed_search_pool(ctx, "qrefine")
    return {"serp_cache_key": cache_key, "query": query, "limit": 5, "offset": 0, "mode": "quick"}


async def _setup_query_serp_click(ctx: LiveCtx) -> JsonObject:
    return {
        "serp_cache_key": f"live-{ctx.unique_id}",
        "query": f"live click {ctx.unique_id}",
        "mode": "quick",
        "url": f"https://live.test/{ctx.unique_id}",
        "position": 1,
        "provider": "index",
        "search_index_id": "runet",
    }


async def _setup_empty(ctx: LiveCtx) -> JsonObject:
    _ = ctx
    return {}


async def _setup_providers_update(ctx: LiveCtx) -> JsonObject:
    _ = ctx
    return {"provider_id": "tavily", "enabled": True, "credential_source": "platform", "timeout_seconds": 12}


async def _setup_providers_order_update(ctx: LiveCtx) -> JsonObject:
    _ = ctx
    return {"provider_order": ["tavily", "serper", "tinyfish", "linkup"]}


async def _setup_providers_reset(ctx: LiveCtx) -> JsonObject:
    _ = ctx
    return {"provider_id": "tavily"}


_CASES: dict[str, OpCase] = {
    "search/crawl_profiles/list_requested": OpCase(
        RestMirror("GET", f"{_API}/crawl/profiles", "query"), _setup_profiles_list, True, "normalized"
    ),
    "search/crawl_profiles/create_requested": OpCase(
        RestMirror("POST", f"{_API}/crawl/profiles", "body_minus_path"), _setup_profiles_create, False, "normalized"
    ),
    "search/crawl_profiles/update_requested": OpCase(
        RestMirror("PATCH", f"{_API}/crawl/profiles/{{crawl_profile_id}}", "body_minus_path"),
        _setup_profiles_update,
        True,
        "normalized",
    ),
    "search/crawl_profiles/summary_requested": OpCase(
        RestMirror("GET", f"{_API}/crawl/profiles/{{crawl_profile_id}}/summary", "none"),
        _setup_profiles_summary,
        True,
        "normalized",
    ),
    "search/crawl_profiles/tranco_seed_requested": OpCase(
        RestMirror("POST", f"{_API}/crawl/profiles/{{crawl_profile_id}}/seed/tranco", "body_minus_path"),
        _setup_profiles_tranco_seed,
        True,
        "normalized",
    ),
    "search/crawl_jobs/queue_requested": OpCase(
        RestMirror("POST", f"{_API}/crawl/jobs", "body_minus_path"), _setup_jobs_queue, True, "normalized"
    ),
    "search/crawl_jobs/list_requested": OpCase(
        RestMirror("GET", f"{_API}/crawl/jobs", "query"), _setup_jobs_list, True, "normalized"
    ),
    "search/crawl_jobs/get_requested": OpCase(
        RestMirror("GET", f"{_API}/crawl/jobs/{{crawl_job_id}}", "none"), _setup_jobs_get, True, "normalized"
    ),
    "search/crawl_domains/list_requested": OpCase(
        RestMirror("GET", f"{_API}/crawl/domains", "query"), _setup_domains_list, True, "normalized"
    ),
    "search/crawl_domains/create_requested": OpCase(
        RestMirror("POST", f"{_API}/crawl/profiles/{{crawl_profile_id}}/domains", "body_minus_path"),
        _setup_domains_create,
        False,
        "normalized",
    ),
    "search/crawl_domains/update_requested": OpCase(
        RestMirror("PATCH", f"{_API}/crawl/domains/{{crawl_domain_id}}", "body_profile_query"),
        _setup_domains_update,
        True,
        "normalized",
    ),
    "search/crawl_domains/remove_requested": OpCase(
        RestMirror("DELETE", f"{_API}/crawl/domains/{{crawl_domain_id}}", "query"),
        _setup_domains_remove,
        False,
        "normalized",
    ),
    "search/crawl_domains/run_requested": OpCase(
        RestMirror("POST", f"{_API}/crawl/domains/{{crawl_domain_id}}/run", "query"),
        _setup_domains_run,
        False,
        "normalized",
    ),
    "search/crawl_domains/urls_add_requested": OpCase(
        RestMirror("POST", f"{_API}/crawl/domains/{{crawl_domain_id}}/urls", "body_profile_query"),
        _setup_domains_urls_add,
        False,
        "normalized",
    ),
    "search/crawl_urls/list_requested": OpCase(
        RestMirror("GET", f"{_API}/crawl/urls", "query"), _setup_urls_list, True, "normalized"
    ),
    "search/crawl_urls/get_requested": OpCase(
        RestMirror("GET", f"{_API}/crawl/urls/{{crawl_url_id}}", "query"), _setup_urls_get, True, "normalized"
    ),
    "search/crawl_urls/recrawl_requested": OpCase(
        RestMirror("POST", f"{_API}/crawl/urls/{{crawl_url_id}}/recrawl", "query"),
        _setup_urls_recrawl,
        True,
        "normalized",
    ),
    "search/crawl_seed/import_requested": OpCase(
        RestMirror("POST", f"{_API}/crawl/seed/import", "body_minus_path"), _setup_seed_import, True, "normalized"
    ),
    "search/indexes/list_requested": OpCase(
        RestMirror("GET", f"{_API}/search-indexes", "query"), _setup_indexes_list, True, "normalized"
    ),
    "search/indexes/get_requested": OpCase(
        RestMirror("GET", f"{_API}/search-indexes/{{search_index_id}}", "none"), _setup_indexes_get, True, "normalized"
    ),
    "search/indexes/create_requested": OpCase(
        RestMirror("POST", f"{_API}/search-indexes", "body_minus_path"), _setup_indexes_create, False, "normalized"
    ),
    "search/indexes/update_requested": OpCase(
        RestMirror("PATCH", f"{_API}/search-indexes/{{search_index_id}}", "body_minus_path"),
        _setup_indexes_update,
        True,
        "normalized",
    ),
    "search/indexes/batch_get_requested": OpCase(
        RestMirror("POST", f"{_API}/search-indexes/batch-get", "body_minus_path"),
        _setup_indexes_batch_get,
        True,
        "normalized",
    ),
    "search/query/search_requested": OpCase(
        RestMirror("POST", f"{_API}/search", "body_minus_path"), _setup_query_search, True, "normalized"
    ),
    "search/query/serp_more_requested": OpCase(
        RestMirror("POST", f"{_API}/search/serp/more", "body_minus_path"), _setup_query_serp_more, True, "normalized"
    ),
    "search/query/serp_refine_requested": OpCase(
        RestMirror("POST", f"{_API}/search/serp/refine", "body_minus_path"),
        _setup_query_serp_refine,
        True,
        "normalized",
    ),
    "search/query/serp_click_requested": OpCase(
        RestMirror("POST", f"{_API}/search/serp/click", "body_minus_path"), _setup_query_serp_click, True, "exact"
    ),
    "search/query/providers_snapshot_requested": OpCase(
        RestMirror("GET", f"{_API}/providers", "none"), _setup_empty, True, "exact"
    ),
    "search/providers/list_requested": OpCase(
        RestMirror("GET", f"{_API}/providers/company", "none"), _setup_empty, True, "exact"
    ),
    "search/providers/update_requested": OpCase(
        RestMirror("PUT", f"{_API}/providers/company/{{provider_id}}", "body_minus_path"),
        _setup_providers_update,
        True,
        "exact",
    ),
    "search/providers/order_update_requested": OpCase(
        RestMirror("PUT", f"{_API}/providers/company/order", "body_minus_path"),
        _setup_providers_order_update,
        True,
        "exact",
    ),
    "search/providers/reset_requested": OpCase(
        RestMirror("DELETE", f"{_API}/providers/company/{{provider_id}}", "none"),
        _setup_providers_reset,
        True,
        "exact",
    ),
}


async def _ws_command(
    *,
    auth_token: str,
    realtime_session_client: AsyncClient,
    canonical_type: str,
    payload: JsonObject,
    timeout_sec: float = 20.0,
) -> JsonObject:
    token_data = get_token_service().validate_token(auth_token)
    if token_data is None:
        raise AssertionError("SESSION JWT is required")
    event_id = uuid.uuid4().hex
    succeeded = canonical_type[: -len("_requested")] + "_succeeded"
    failed = canonical_type[: -len("_requested")] + "_failed"
    async with connect_centrifugo(auth_token) as ws:
        accepted = await rpc_platform_event(
            ws,
            event_type=canonical_type,
            payload=payload,
            company_id=token_data.company_id,
            event_id=event_id,
        )
        assert accepted.get("accepted") is True
        assert accepted.get("event_id") == event_id
        deadline = asyncio.get_running_loop().time() + timeout_sec
        terminal_ws: JsonObject | None = None
        while asyncio.get_running_loop().time() < deadline:
            remaining = deadline - asyncio.get_running_loop().time()
            event = await ws.recv_platform_event(timeout=remaining)
            if event.get("type") not in (succeeded, failed):
                continue
            meta = event.get("meta")
            if not isinstance(meta, dict) or meta.get("causation_id") != event_id:
                continue
            terminal_ws = event
            break
    if terminal_ws is None:
        raise AssertionError(f"WS reply для {canonical_type!r} event_id={event_id} не получен")
    terminal_http = await realtime_session_client.get(f"/realtime/api/v1/events/{event_id}/terminal")
    assert terminal_http.status_code == 200, terminal_http.text
    terminal = require_json_object(terminal_http.json(), "terminal")
    assert terminal["type"] == terminal_ws["type"]
    return terminal_ws


async def _rest_command(
    *,
    client: AsyncClient,
    headers: dict[str, str],
    rest: RestMirror,
    payload: JsonObject,
) -> JsonObject:
    path_params = {key: _str_field(payload, key) for key in _PATH_PLACEHOLDER.findall(rest.url)}
    url = rest.url.format(**path_params)
    json_body: JsonObject | None = None
    query: dict[str, JsonValue] | None = None
    if rest.strategy == "body_minus_path":
        body = {k: v for k, v in payload.items() if k not in path_params and v is not None}
        json_body = body if body else None
    elif rest.strategy == "body_profile_query":
        body = {
            k: v for k, v in payload.items() if k not in path_params and k != "crawl_profile_id" and v is not None
        }
        json_body = body if body else None
        query = {"crawl_profile_id": _str_field(payload, "crawl_profile_id")}
    elif rest.strategy == "query":
        query = {k: v for k, v in payload.items() if k not in path_params and v is not None}
    response = await client.request(rest.method, url, headers=headers, json=json_body, params=query)
    return await _expect_json(response, ok=(200, 201, 202, 204), label=f"REST {rest.method} {url}")


def test_every_search_operation_has_live_case() -> None:
    missing = sorted(set(SEARCH_OPERATIONS) - set(_CASES))
    extra = sorted(set(_CASES) - set(SEARCH_OPERATIONS))
    assert not missing, f"нет live-кейса для {missing}"
    assert not extra, f"лишние live-кейсы {extra}"


@pytest.mark.asyncio
@pytest.mark.timeout(90)
@pytest.mark.parametrize("canonical_type", sorted(_CASES))
async def test_search_op_ws_rest_identical(
    canonical_type: str,
    search_service: None,
    rag_service: None,
    realtime_service: None,
    search_client_http: AsyncClient,
    rag_client_http: AsyncClient,
    realtime_session_client: AsyncClient,
    auth_headers_system: dict[str, str],
    auth_token_system: str,
    unique_id: str,
    search_worker_prerequisites: None,
) -> None:
    _ = search_service, rag_service, realtime_service, search_worker_prerequisites
    case = _CASES[canonical_type]
    ws_ctx = LiveCtx(
        client=search_client_http,
        rag_client=rag_client_http,
        headers=auth_headers_system,
        unique_id=unique_id,
        suffix="ws",
    )
    ws_payload = await case.setup(ws_ctx)
    ws_event = await _ws_command(
        auth_token=auth_token_system,
        realtime_session_client=realtime_session_client,
        canonical_type=canonical_type,
        payload=ws_payload,
    )
    assert str(ws_event["type"]).endswith("_succeeded"), (
        f"WS {canonical_type} вернул {ws_event['type']}: {ws_event.get('payload')}"
    )
    ws_result = _event_payload(ws_event)
    if case.same_resource:
        rest_payload = ws_payload
    else:
        rest_payload = await case.setup(
            LiveCtx(
                client=search_client_http,
                rag_client=rag_client_http,
                headers=auth_headers_system,
                unique_id=unique_id,
                suffix="rest",
            )
        )
    rest_result = await _rest_command(
        client=search_client_http,
        headers=auth_headers_system,
        rest=case.rest,
        payload=rest_payload,
    )
    if case.compare == "exact":
        assert ws_result == rest_result, f"WS != REST для {canonical_type}\nWS: {ws_result}\nREST: {rest_result}"
    else:
        assert _normalize(ws_result) == _normalize(rest_result), (
            f"WS != REST для {canonical_type}\nWS: {ws_result}\nREST: {rest_result}"
        )


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_search_index_missing_failed_terminal(
    search_service: None,
    realtime_service: None,
    realtime_session_client: AsyncClient,
    auth_token_system: str,
    unique_id: str,
) -> None:
    _ = search_service, realtime_service
    event = await _ws_command(
        auth_token=auth_token_system,
        realtime_session_client=realtime_session_client,
        canonical_type="search/indexes/get_requested",
        payload={"search_index_id": f"missing_{unique_id}".lower().replace("-", "_")},
    )
    assert event["type"] == "search/indexes/get_failed"
    assert _event_payload(event)["error_code"] == "not_found"
