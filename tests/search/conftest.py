import pytest
import pytest_asyncio

import apps.search_worker.tasks.crawl_tasks as _search_crawl_tasks  # noqa: F401
from apps.search.config import SearchIntegrationConfig, get_search_settings, reset_search_settings
from apps.search.container import SearchContainer, get_search_container, reset_search_container
from apps.search.services import MetaSearchService
from apps.search.services.provider_availability import ProviderAvailabilityStore
from core.clients.redis_client import RedisClient
from core.config import get_settings
from core.search.index_models import SearchIndexCrawlTaxonomy

_SEARCH_PROVIDER_AVAILABILITY_SCOPES = ("platform", "company_system")

_TEST_CRAWL_TAXONOMY = SearchIndexCrawlTaxonomy(
    primary_topics=["tech", "other", "documentation"],
    topic_tags=["tech", "software", "other", "documentation", "faq"],
    category_paths=[["tech"], ["other"]],
)


@pytest.fixture(autouse=True)
def crawl_taxonomy_for_search_tests(monkeypatch):
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


@pytest.fixture
def search_container(setup_database_before_tests) -> SearchContainer:
    _ = setup_database_before_tests
    reset_search_container()
    container = get_search_container()
    yield container
    reset_search_container()


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
    search_container: SearchContainer,
) -> MetaSearchService:
    return MetaSearchService(
        config,
        store,
        search_container.billing_service,
        search_container.index_search_provider,
        search_container.serp_cache_service,
    )


@pytest.fixture
def meta_search_service_builder(search_container):
    def _build(
        config: SearchIntegrationConfig,
        store: ProviderAvailabilityStore,
    ) -> MetaSearchService:
        return build_meta_search_service(config, store, search_container)

    return _build


def make_search_index_slug(unique_id: str) -> str:
    slug = f"idx_{unique_id}".lower().replace("-", "_")
    return slug[:63]


@pytest.fixture
def search_crawl_low_min_extract_chars(monkeypatch):
    monkeypatch.setenv("CRAWL__MIN_EXTRACT_CHARS", "50")
    reset_search_settings()
    reset_search_container()
    yield
    monkeypatch.delenv("CRAWL__MIN_EXTRACT_CHARS", raising=False)
    reset_search_settings()
    reset_search_container()


@pytest.fixture
def crawl_search_container(search_crawl_low_min_extract_chars, setup_database_before_tests):
    _ = search_crawl_low_min_extract_chars, setup_database_before_tests
    reset_search_container()
    container = get_search_container()
    yield container
    reset_search_container()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def ensure_platform_search_worker_prerequisites(
    setup_database_before_tests,
    frontend_container,
):
    """Worker context (build_search_system_context) и seed runet требуют system admin email."""
    _ = setup_database_before_tests
    from core.identity.system_bootstrap import (
        ADMIN_ROLE,
        SYSTEM_ADMIN_EMAIL,
        SYSTEM_COMPANY_ID,
        ensure_system_admin_membership,
        ensure_system_company_exists,
    )
    from core.models.identity_models import User

    company = await ensure_system_company_exists(
        company_repository=frontend_container.company_repository,
        subdomain_repository=frontend_container.subdomain_repository,
    )
    _, admin_user = await ensure_system_admin_membership(
        company_repository=frontend_container.company_repository,
        subdomain_repository=frontend_container.subdomain_repository,
        user_repository=frontend_container.user_repository,
    )
    if admin_user is None:
        admin_user_id = "user_zambas124_yandex_ru_test"
        admin_user = User(
            user_id=admin_user_id,
            name="Platform System Admin",
            emails=[SYSTEM_ADMIN_EMAIL],
            companies={SYSTEM_COMPANY_ID: [ADMIN_ROLE]},
        )
        await frontend_container.user_repository.set(admin_user)
        member_roles = list(company.members.get(admin_user_id, []))
        if ADMIN_ROLE not in member_roles:
            member_roles.append(ADMIN_ROLE)
        company.members[admin_user_id] = member_roles
        await frontend_container.company_repository.set(company)

    from tests.fixtures.search_runet import ensure_runet_platform_index_seeded

    await ensure_runet_platform_index_seeded()


@pytest_asyncio.fixture
async def search_system_context(search_container, unique_id, auth_token_system):
    from core.context import clear_context, set_context
    from core.models.context_models import Context
    from core.models.i18n_models import Language
    from core.models.identity_models import Company, User
    from core.utils.tokens import get_token_service

    token_data = get_token_service().validate_token(auth_token_system)
    if token_data is None:
        raise ValueError("Invalid auth token")
    user_record = await search_container.user_repository.get(token_data.user_id)
    if user_record is None:
        raise ValueError(f"User {token_data.user_id} not found")
    company_record = await search_container.company_repository.get(token_data.company_id)
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
