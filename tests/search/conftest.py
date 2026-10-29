import pytest
import pytest_asyncio

from apps.search.config import SearchIntegrationConfig, get_search_settings, reset_search_settings
from apps.search.di import SearchDi
from apps.search.services.meta import MetaSearchService
from apps.search.services.provider_availability import ProviderAvailabilityStore
from apps.worker_manifest import wire_worker
from core.clients.redis_client import RedisClient
from core.config import get_settings
from core.di import open_di
from core.di.kit import ProcessIdentity
from core.files.urls import resolve_files_route_segment
from core.models.identity_models import Company
from core.search.index_models import SearchIndexCrawlTaxonomy

_ = wire_worker("search")
import apps.search.tasks.crawl_tasks as _search_crawl_tasks  # noqa: E402, F401

_SEARCH_PROVIDER_AVAILABILITY_SCOPES = ("platform", "company_system")

_TEST_CRAWL_TAXONOMY = SearchIndexCrawlTaxonomy(
    primary_topics=["tech", "other", "documentation"],
    topic_tags=["tech", "software", "other", "documentation", "faq"],
    category_paths=[["tech"], ["other"]],
)


@pytest.fixture(autouse=True)
def crawl_taxonomy_for_search_tests(request: pytest.FixtureRequest) -> None:
    """Search taxonomy stub.

    Подключается и как ``tests/search/conftest``, и через ``pytest_plugins``
    из отдельных cross-service модулей. ``monkeypatch`` нельзя объявлять
    параметром фикстуры: иначе он попадает в ``fixturenames`` всех тестов
    worker'а и ломает ``no_test_doubles``.
    """
    if request.node.get_closest_marker("no_test_doubles") is not None:
        return

    monkeypatch = request.getfixturevalue("monkeypatch")
    if not isinstance(monkeypatch, pytest.MonkeyPatch):
        raise TypeError("monkeypatch fixture must be pytest.MonkeyPatch")

    def _resolve(search_index_id: str) -> SearchIndexCrawlTaxonomy:
        _ = search_index_id
        return _TEST_CRAWL_TAXONOMY

    monkeypatch.setattr(
        "apps.search.services.crawl.page_enrichment_service.resolve_crawl_taxonomy",
        _resolve,
    )


@pytest.fixture(autouse=True)
async def reset_index_provider_availability_before_search_test(request):
    if request.node.get_closest_marker("unit") is not None:
        yield
        return
    redis_client = RedisClient(get_settings().database.redis_url)
    await redis_client.connect()
    prefix = get_search_settings().search.provider_state_key_prefix
    store = ProviderAvailabilityStore(
        redis_client,
        key_prefix=prefix,
        available_ttl_seconds=300,
        unavailable_ttl_seconds=300,
    )
    try:
        for scope_id in _SEARCH_PROVIDER_AVAILABILITY_SCOPES:
            await store.clear("index", scope_id=scope_id)
        yield
    finally:
        await redis_client.close()


async def _open_search_di():
    async with open_di(
        SearchDi,
        settings=get_search_settings(),
        identity=ProcessIdentity(
            service_name="search",
            files_route_segment=resolve_files_route_segment("search"),
        ),
        database="search_url",
    ) as di:
        yield di


@pytest_asyncio.fixture
async def search_di(setup_database_before_tests):
    _ = setup_database_before_tests
    async for di in _open_search_di():
        yield di


@pytest.fixture
async def provider_state_store(unique_id):
    client = RedisClient(get_settings().database.redis_url)
    await client.connect()
    store = ProviderAvailabilityStore(
        client,
        key_prefix=f"test:search:providers:{unique_id}",
        available_ttl_seconds=300,
        unavailable_ttl_seconds=300,
    )
    try:
        yield store
    finally:
        await client.close()


def build_meta_search_service(
    config: SearchIntegrationConfig,
    store: ProviderAvailabilityStore,
    search_di,
) -> MetaSearchService:
    meta = search_di.meta_search_service
    return MetaSearchService(
        config,
        store,
        search_di.billing_service,
        meta._index_provider,
        meta._serp_cache_service,
    )


@pytest.fixture
def meta_search_service_builder(search_di):
    def _build(
        config: SearchIntegrationConfig,
        store: ProviderAvailabilityStore,
    ) -> MetaSearchService:
        return build_meta_search_service(config, store, search_di)

    return _build


def make_search_index_slug(unique_id: str) -> str:
    slug = f"idx_{unique_id}".lower().replace("-", "_")
    return slug[:63]


@pytest.fixture
def search_crawl_low_min_extract_chars(monkeypatch):
    monkeypatch.setenv("CRAWL__MIN_EXTRACT_CHARS", "50")
    reset_search_settings()
    yield
    monkeypatch.delenv("CRAWL__MIN_EXTRACT_CHARS", raising=False)
    reset_search_settings()


@pytest_asyncio.fixture
async def crawl_search_di(search_crawl_low_min_extract_chars, setup_database_before_tests):
    _ = search_crawl_low_min_extract_chars, setup_database_before_tests
    async for di in _open_search_di():
        yield di


@pytest.fixture
def enable_serp_rerank(monkeypatch):
    """Включает SERP refine (reranker) — в общем conftest по умолчанию выключен."""
    monkeypatch.setenv("RAG__DOCUMENT_INDEXING__SEARCH_DEFAULTS__RERANKER__ENABLED", "true")
    import core.config.base as config_base

    config_base._settings_instance = None
    reset_search_settings()
    yield
    config_base._settings_instance = None
    reset_search_settings()

@pytest_asyncio.fixture(scope="session", autouse=True)
async def ensure_platform_search_worker_prerequisites(search_worker_prerequisites) -> None:
    _ = search_worker_prerequisites


@pytest_asyncio.fixture
async def search_system_context(search_di, unique_id, auth_token_system):
    from core.context import clear_context, set_context
    from core.models.context_models import Context
    from core.models.i18n_models import Language
    from core.models.identity_models import User
    from core.utils.tokens import get_token_service

    token_data = get_token_service().validate_token(auth_token_system)
    if token_data is None:
        raise ValueError("Invalid auth token")
    user_record = await User.get(token_data.user_id)
    if user_record is None:
        raise ValueError(f"User {token_data.user_id} not found")
    company_record = await Company.get(token_data.company_id)
    if company_record is None:
        raise ValueError(f"Company {token_data.company_id} not found")

    ctx = Context(
        user=User(
            user_id=user_record.user_id,
            name=user_record.name or user_record.user_id,
            groups=user_record.groups,
        ),
        host="system",
        session_id=f"search:{unique_id}",
        channel="test",
        language=Language.RU,
        active_company=Company(
            company_id=company_record.company_id,
            name=company_record.name,
            subdomain=company_record.subdomain,
        ),
        user_companies=[],
        trace_id=f"test:search:{unique_id}",
        auth_token=auth_token_system,
    )
    set_context(ctx)
    try:
        yield ctx
    finally:
        clear_context()
