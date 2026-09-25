"""FastAPI entrypoint for search service."""

from collections.abc import AsyncIterator

from apps.search.api.mcp import router as search_mcp_router
from apps.search.api.v1.crawl import router as crawl_v1_router
from apps.search.api.v1.search import router as search_v1_router
from apps.search.api.v1.search_indexes import router as search_indexes_v1_router
from apps.search.api.v1.search_providers import router as search_providers_v1_router
from apps.search.config import SearchSettings, get_search_settings
from apps.search.di import SearchDi
from apps.search.realtime.command_router import SEARCH_OPERATIONS
from core.app.factory import create_service_app
from core.clients.redis_client import RedisClient
from core.di import recipe


async def connect_search_redis(redis_client: RedisClient) -> AsyncIterator[None]:
    """Соединение Redis до обслуживания; закрытие делает recipe ``PlatformDi``."""
    await redis_client.connect()
    yield


app = create_service_app(
    "search",
    SearchSettings,
    SearchDi,
    database="search_url",
    operations=SEARCH_OPERATIONS,
    lifecycle=(recipe(connect_search_redis),),
    routers=[
        search_mcp_router,
        search_v1_router,
        search_indexes_v1_router,
        search_providers_v1_router,
        crawl_v1_router,
    ],
    cors_origins=["*"],
    title="Platform Search",
    description="Search provider gateway and MCP server",
    version="1.0.0",
    api_version="v1",
    include_platform_routers=False,
    mount_repo_documentation=False,
    include_platform_pwa=False,
)


if __name__ == "__main__":  # pragma: no cover
    from core.app.server import serve

    serve("search", "apps.search.main:app", get_search_settings())
