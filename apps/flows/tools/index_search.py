"""Platform index and web meta-search tools for flows."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from apps.flows.src.tools.decorator import tool
from core.clients.search_client import SearchClient
from core.clients.service_client import ServiceClientError
from core.models import StrictBaseModel
from core.search.models import MetaSearchRequest, SearchMode
from core.types import JsonObject


class IndexSearchToolArgs(StrictBaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    search_index_ids: list[str] = Field(..., min_length=1, max_length=5)
    limit: int = Field(default=8, ge=1, le=20)


async def _index_search_impl(
    query: str,
    search_index_ids: list[str],
    limit: int = 8,
) -> JsonObject:
    client = SearchClient()
    try:
        response = await client.search(
            MetaSearchRequest(
                query=query,
                limit=limit,
                providers=["index"],
                index_ids=search_index_ids,
            )
        )
    except ServiceClientError as exc:
        return {"success": False, "error": str(exc)}
    return {"success": True, "response": response.model_dump(mode="json")}


@tool(
    name="index_search",
    description="Hybrid search across platform RAG indexes by search_index_id slug",
    tags=["web"],
    parameters_model=IndexSearchToolArgs,
)
async def index_search(
    query: str,
    search_index_ids: list[str],
    limit: int = 8,
) -> JsonObject:
    return await _index_search_impl(
        query=query,
        search_index_ids=search_index_ids,
        limit=limit,
    )


class RunetSearchToolArgs(StrictBaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    limit: int = Field(default=8, ge=1, le=20)


@tool(
    name="runet_search",
    description="Hybrid search in the runet platform index",
    tags=["web"],
    parameters_model=RunetSearchToolArgs,
)
async def runet_search(query: str, limit: int = 8) -> JsonObject:
    return await _index_search_impl(
        query=query,
        search_index_ids=["runet"],
        limit=limit,
    )


class WebSearchToolArgs(StrictBaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    limit: int = Field(default=10, ge=1, le=25)
    providers: list[str] = Field(default_factory=lambda: ["auto"], max_length=8)
    provider_strategy: Literal["first_available", "merge"] = "merge"
    language: str = Field(default="ru", min_length=2, max_length=12)
    region: str = Field(default="ru", min_length=2, max_length=12)
    mode: SearchMode = "research"


@tool(
    name="web_search",
    description=(
        "Meta web search across platform providers (index/runet, TinyFish, Linkup, "
        "Serper/Google, Tavily). Returns normalized, ranked results with per-provider status. "
        "Use provider_strategy='merge' with providers=['auto'] for broad research coverage."
    ),
    tags=["web"],
    parameters_model=WebSearchToolArgs,
)
async def web_search(
    query: str,
    providers: list[str],
    provider_strategy: Literal["first_available", "merge"] = "merge",
    language: str = "ru",
    region: str = "ru",
    mode: SearchMode = "research",
    limit: int = 10,
) -> JsonObject:
    client = SearchClient()
    try:
        response = await client.search(
            MetaSearchRequest(
                query=query,
                limit=limit,
                providers=providers,
                provider_strategy=provider_strategy,
                language=language,
                region=region,
                mode=mode,
            )
        )
    except ServiceClientError as exc:
        return {"success": False, "error": str(exc)}
    results: list[JsonObject] = [
        {
            "title": item.title,
            "url": item.url,
            "snippet": item.snippet,
            "display_url": item.display_url,
            "provider": item.provider,
            "provider_rank": item.provider_rank,
            "site_name": item.site_name,
            "published_at": item.published_at,
        }
        for item in response.results
    ]
    providers_status: JsonObject = {
        name: {
            "ok": status.ok,
            "results_count": status.results_count,
            "error": status.error,
        }
        for name, status in response.providers.items()
    }
    return {
        "success": True,
        "results": results,
        "providers": providers_status,
        "total_count": response.total_count,
    }
