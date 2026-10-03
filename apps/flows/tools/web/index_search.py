"""Platform index and web meta-search tools for flows."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from apps.flows.src.tools.decorator import tool
from core.clients.search_client import SearchClient
from core.models import StrictBaseModel
from core.search.models import MetaSearchRequest, SearchMode
from core.types import JsonObject, require_json_object


class IndexSearchToolArgs(StrictBaseModel):
    query: str = Field(..., min_length=1, max_length=500, description="Search query text.")
    search_index_ids: list[str] = Field(
        ...,
        min_length=1,
        max_length=5,
        description="Platform search_index slugs to search (1-5).",
    )
    limit: int = Field(default=8, ge=1, le=20, description="Max results returned.")


async def _index_search_impl(
    query: str,
    search_index_ids: list[str],
    limit: int = 8,
) -> JsonObject:
    response = await SearchClient().search(
        MetaSearchRequest(
            query=query,
            limit=limit,
            providers=["index"],
            index_ids=search_index_ids,
        )
    )
    return require_json_object(response.model_dump(mode="json"), "index_search")


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
    query: str = Field(..., min_length=1, max_length=500, description="Search query text.")
    limit: int = Field(default=8, ge=1, le=20, description="Max results returned.")


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
    query: str = Field(..., min_length=1, max_length=500, description="Search query text.")
    limit: int = Field(default=10, ge=1, le=25, description="Max results returned.")
    providers: list[str] = Field(
        default_factory=lambda: ["auto"],
        max_length=8,
        description="Provider slugs (index, runet, tinyfish, linkup, serper, tavily); 'auto' lets the server pick.",
    )
    provider_strategy: Literal["first_available", "merge"] = Field(
        "merge",
        description=(
            "first_available — first provider that returns results; "
            "merge — fuse ranked results from all providers."
        ),
    )
    language: str = Field(
        default="ru",
        min_length=2,
        max_length=12,
        description="ISO language code for the query, e.g. ru or en.",
    )
    region: str = Field(
        default="ru",
        min_length=2,
        max_length=12,
        description="Region code for provider localization, e.g. ru.",
    )
    mode: SearchMode = Field(
        "research",
        description="Search mode preset controlling depth/crawling (SearchMode).",
    )


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
    response = await SearchClient().search(
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
    return require_json_object(response.model_dump(mode="json"), "web_search")
