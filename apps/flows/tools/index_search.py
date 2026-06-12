"""Platform index search tool for flows."""

from __future__ import annotations

from pydantic import Field

from apps.flows.src.tools.decorator import tool
from core.clients.search_client import SearchClient
from core.clients.service_client import ServiceClientError
from core.models import StrictBaseModel
from core.search.models import MetaSearchRequest
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
    tags=["search", "index"],
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
    tags=["search", "runet"],
    parameters_model=RunetSearchToolArgs,
)
async def runet_search(query: str, limit: int = 8) -> JsonObject:
    return await _index_search_impl(
        query=query,
        search_index_ids=["runet"],
        limit=limit,
    )
