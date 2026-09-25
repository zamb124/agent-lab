import pytest
from pydantic import ValidationError

from apps.search.config import (
    SearchIntegrationConfig,
    SearchSettings,
    get_search_settings,
    reset_search_settings,
)
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


def test_search_settings_are_loadable() -> None:
    reset_search_settings()

    settings = get_search_settings()

    assert settings.server.name == "search"
    assert settings.search.provider_order == ["tinyfish", "linkup", "serper", "tavily"]
    assert settings.search.tinyfish.enabled is True
    assert settings.search.linkup.enabled is True
    assert settings.search.serper.enabled is True
    assert settings.search.tavily.enabled is True
    runet_taxonomy = settings.crawl.taxonomies["runet"]
    assert len(runet_taxonomy.primary_topics) >= 100
    assert len(runet_taxonomy.topic_tags) >= 250
    assert len(runet_taxonomy.category_paths) >= 200

    reset_search_settings()


def test_search_settings_require_search_database_url() -> None:
    with pytest.raises(ValueError, match="database.search_url is required"):
        SearchSettings.model_validate({"database": {"search_url": "", "shared_url": "postgresql://localhost/shared"}})


@pytest.mark.asyncio
async def test_connect_search_redis_pings() -> None:
    from apps.search.main import connect_search_redis

    settings = get_search_settings()
    from core.clients.redis_client import RedisClient

    redis_client = RedisClient(settings.database.redis_url)
    lifecycle = connect_search_redis(redis_client)
    await anext(lifecycle)
    try:
        assert await redis_client.ping() is True
    finally:
        await lifecycle.aclose()
        await redis_client.close()
