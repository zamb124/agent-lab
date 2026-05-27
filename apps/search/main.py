"""FastAPI entrypoint for search service."""

from fastapi import FastAPI

from apps.search.api.mcp import router as search_mcp_router
from apps.search.config import SearchSettings, get_search_settings
from apps.search.container import SearchContainer, get_search_container
from core.app import create_service_app


async def on_startup(_app: FastAPI, container: SearchContainer, _settings: SearchSettings) -> None:
    await container.redis_client.connect()


async def on_shutdown(_app: FastAPI, container: SearchContainer) -> None:
    await container.redis_client.close()


app = create_service_app(
    service_name="search",
    settings_class=SearchSettings,
    get_container=get_search_container,
    routers=[search_mcp_router],
    cors_origins=["*"],
    title="Platform Search",
    description="Search provider gateway and MCP server",
    version="1.0.0",
    api_version="v1",
    include_crud_routers=False,
    include_platform_routers=False,
    mount_repo_documentation=False,
    include_platform_pwa=False,
    on_startup=on_startup,
    on_shutdown=on_shutdown,
)


if __name__ == "__main__":  # pragma: no cover
    from core.app.server import serve

    serve("search", "apps.search.main:app", get_search_settings())
