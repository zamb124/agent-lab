"""
Фикстуры сервиса wiki (shared; не импортировать tests.wiki.conftest как pytest_plugins).

Тесты идут по продовому пути целиком: реальный Postgres, реальный RAG на
стеке `make test-up`, настоящий `AuthMiddleware` и настоящая проверка
пространства. Подмен и заглушек здесь нет — индексация страницы включена
всегда, поэтому запись без поднятого RAG просто не пройдёт, и это правильное
поведение, а не повод подставить двойника.

HTTP: `wiki_client` (владелец в `system`), `wiki_client_member` (второй
пользователь той же компании), `wiki_client_company2` (чужая компания).
Домен: `wiki_di`, `wiki_service`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from apps.wiki.di import WikiDi
from apps.wiki.models.domain import WikiPage
from apps.wiki.services.rag_index import WikiRagIndexService
from apps.wiki.services.wiki_service import WikiService
from core.di import require_di
from core.namespace.service import NamespaceService
from tests.fixtures.auth import service_client_asgi_auth_context
from tests.fixtures.platform_events import (
    PlatformEventsReceive,
)
from tests.fixtures.platform_events import (
    platform_events_listener as open_platform_events_stream,
)
from tests.fixtures.service_processes import ServiceProcesses

API_PREFIX = "/wiki/api/v1"
PAGES_URL = f"{API_PREFIX}/pages"

NAMESPACE_HEADER = "X-Platform-Namespace"


@pytest_asyncio.fixture
async def wiki_di(wiki_app) -> WikiDi:
    """Тот же ``WikiDi``, что собрал lifespan ``wiki_app``."""
    return require_di(wiki_app, WikiDi)


@pytest.fixture
def wiki_service(request: pytest.FixtureRequest) -> WikiService:
    opened = request.getfixturevalue("wiki_di")
    if not isinstance(opened, WikiDi):
        raise TypeError("wiki DI is not open")
    return opened.wiki_service


@pytest.fixture
def wiki_rag_index(wiki_service: WikiService) -> WikiRagIndexService:
    return wiki_service._rag


@pytest_asyncio.fixture
async def wiki_app(rag_service, service_processes: ServiceProcesses):
    """ASGI-приложение сервиса с lifespan (``service_processes``).

    RAG обязателен: каждое сохранение страницы пишет её в индекс.
    """
    _ = rag_service
    return await service_processes.app("wiki")


@pytest_asyncio.fixture
async def wiki_namespace(wiki_di, unique_id: str) -> str:
    """Отдельное пространство на тест — граница изоляции данных."""
    from core.context import clear_context, set_context
    from core.models.context_models import Context
    from core.models.identity_models import User
    from tests.fixtures.ai_provider_defaults import make_test_company

    service: NamespaceService = wiki_di.namespace_service
    name = f"wiki-test-{unique_id}"
    set_context(
        Context(
            user=User(user_id="test_user", name="Test User"),
            active_company=make_test_company(company_id="system", name="System"),
            session_id="wiki_namespace_setup",
            channel="test",
        )
    )
    try:
        _ = await service.get_or_create(
            name, description=f"Wiki test namespace {unique_id}"
        )
    finally:
        clear_context()
    return name


@pytest_asyncio.fixture
async def wiki_other_namespace(wiki_di, unique_id: str) -> str:
    """Второе пространство той же компании — для проверок изоляции."""
    from core.context import clear_context, set_context
    from core.models.context_models import Context
    from core.models.identity_models import User
    from tests.fixtures.ai_provider_defaults import make_test_company

    service: NamespaceService = wiki_di.namespace_service
    name = f"wiki-other-{unique_id}"
    set_context(
        Context(
            user=User(user_id="test_user", name="Test User"),
            active_company=make_test_company(company_id="system", name="System"),
            session_id="wiki_namespace_setup",
            channel="test",
        )
    )
    try:
        _ = await service.get_or_create(
            name, description=f"Wiki other namespace {unique_id}"
        )
    finally:
        clear_context()
    return name


def _client(app: object, headers: dict[str, str], namespace: str) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={**headers, NAMESPACE_HEADER: namespace},
    )


@pytest_asyncio.fixture
async def wiki_client(wiki_app, wiki_di, auth_headers_system, wiki_namespace) -> AsyncIterator[AsyncClient]:
    _ = wiki_di
    async with _client(wiki_app, auth_headers_system, wiki_namespace) as client:
        yield client


@pytest_asyncio.fixture
async def wiki_client_member(
    wiki_app, wiki_di, auth_headers_system_user2, wiki_namespace
) -> AsyncIterator[AsyncClient]:
    _ = wiki_di
    """Второй пользователь той же компании: видит общие страницы, но не ограниченные."""
    async with _client(wiki_app, auth_headers_system_user2, wiki_namespace) as client:
        yield client


@pytest_asyncio.fixture
async def wiki_client_company2(
    wiki_app, wiki_di, auth_headers_company2, wiki_namespace
) -> AsyncIterator[AsyncClient]:
    _ = wiki_di
    """Пользователь другой компании: пространство ему не принадлежит."""
    async with _client(wiki_app, auth_headers_company2, wiki_namespace) as client:
        yield client


@pytest_asyncio.fixture
async def wiki_client_other_namespace(
    wiki_app, wiki_di, auth_headers_system, wiki_other_namespace
) -> AsyncIterator[AsyncClient]:
    _ = wiki_di
    """Тот же пользователь, другое пространство."""
    async with _client(wiki_app, auth_headers_system, wiki_other_namespace) as client:
        yield client


@pytest_asyncio.fixture
async def wiki_client_anonymous(wiki_app, wiki_di) -> AsyncIterator[AsyncClient]:
    _ = wiki_di
    """Без сессии — только публичные ссылки."""
    async with AsyncClient(
        transport=ASGITransport(app=wiki_app), base_url="http://testserver"
    ) as client:
        yield client


CreatePage = Callable[..., Coroutine[Any, Any, dict[str, Any]]]


@pytest_asyncio.fixture
async def create_page(wiki_client: AsyncClient) -> CreatePage:
    """Создать страницу через публичный API и вернуть её представление."""

    async def _create(
        title: str,
        *,
        markdown: str | None = None,
        parent_page_id: str | None = None,
        client: AsyncClient | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"title": title}
        if markdown is not None:
            body["markdown"] = markdown
        if parent_page_id is not None:
            body["parent_page_id"] = parent_page_id
        response = await (client or wiki_client).post(PAGES_URL, json=body)
        assert response.status_code == 201, response.text
        page = response.json()["page"]
        assert isinstance(page, dict)
        return page

    return _create


@pytest_asyncio.fixture
async def wiki_page(create_page: CreatePage, unique_id: str) -> dict[str, Any]:
    return await create_page(f"Страница {unique_id}", markdown="# Заголовок\n\nТекст страницы.")


@pytest_asyncio.fixture
async def stored_page(wiki_service, wiki_namespace) -> Callable[[str], Coroutine[Any, Any, WikiPage]]:
    """Прочитать страницу из домена — проверка состояния после HTTP-операций."""

    async def _load(wiki_page_id: str) -> WikiPage:
        return await wiki_service.require_page("system", wiki_namespace, wiki_page_id)

    return _load


@pytest.fixture
def wiki_domain_context(auth_headers_system):
    """Контекст с реальным токеном для прямых вызовов сервиса.

    Доменные тесты обходят HTTP, но сервис всё равно ходит в RAG по сети:
    без токена в контексте межсервисный клиент получит 401. Это тот же
    контекст, который в бою ставит `AuthMiddleware`.
    """
    with service_client_asgi_auth_context(auth_headers_system):
        yield


@pytest_asyncio.fixture()
async def platform_events_listener() -> AsyncIterator[PlatformEventsReceive]:
    async with open_platform_events_stream() as receive:
        yield receive
