import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from apps.search.config import (
    SearchIntegrationConfig,
    SearchSettings,
    get_search_settings,
    reset_search_settings,
)
from apps.search.container import (
    _build_search_container,
    get_search_container,
    reset_search_container,
)
from apps.search.dependencies import get_container
from apps.search.main import on_shutdown, on_startup
from core.config.models import ServerConfig
from core.search import MetaSearchRequest


def test_server_config_resolves_search_service_url() -> None:
    cfg = ServerConfig()

    assert cfg.get_service_url("search") == "http://localhost:8010"


def test_meta_search_request_normalizes_providers() -> None:
    assert MetaSearchRequest.model_validate({"query": "q", "providers": None}).providers == ["auto"]
    assert MetaSearchRequest.model_validate({"query": "q", "providers": " Google "}).providers == ["google"]
    assert MetaSearchRequest(query="q", providers=["", "Serper", "serper"]).providers == ["serper"]

    with pytest.raises(ValidationError, match="providers must be a string or an array"):
        MetaSearchRequest.model_validate({"query": "q", "providers": 1})

    with pytest.raises(ValidationError, match=r"providers\[\] must be string"):
        MetaSearchRequest.model_validate({"query": "q", "providers": [1]})


def test_search_integration_config_normalizes_provider_order() -> None:
    config = SearchIntegrationConfig(provider_order=["tinyfish", "tinyfish", "serper"])

    assert config.provider_order == ["tinyfish", "serper"]

    with pytest.raises(ValidationError, match="provider_order must contain at least one provider"):
        SearchIntegrationConfig(provider_order=[])


def test_search_settings_and_container_are_loadable() -> None:
    reset_search_settings()
    reset_search_container()

    settings = get_search_settings()
    container = get_search_container()

    assert settings.server.name == "search"
    assert settings.search.provider_order == ["tinyfish", "linkup", "serper", "tavily"]
    assert settings.search.tinyfish.enabled is True
    assert settings.search.linkup.enabled is True
    assert settings.search.serper.enabled is True
    assert settings.search.tavily.enabled is True
    assert container.meta_search_service is get_container().meta_search_service

    reset_search_container()
    reset_search_settings()


def test_search_container_requires_shared_database_url() -> None:
    settings = SearchSettings.model_validate({"database": {"shared_url": ""}})

    with pytest.raises(ValueError, match="database.shared_url is required"):
        _build_search_container(settings)


@pytest.mark.asyncio
async def test_search_startup_and_shutdown_connect_redis() -> None:
    settings = get_search_settings()
    container = _build_search_container(settings)

    await on_startup(FastAPI(), container, settings)
    try:
        assert await container.redis_client.ping() is True
    finally:
        await on_shutdown(FastAPI(), container)
