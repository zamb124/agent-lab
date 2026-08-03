"""
Фикстуры сервиса wiki.

Тесты идут по продовому пути целиком: реальный Postgres, реальный RAG на
стеке `make test-up`, настоящий `AuthMiddleware` и настоящая проверка
пространства. Подмен и заглушек здесь нет — индексация страницы включена
всегда, поэтому запись без поднятого RAG просто не пройдёт, и это правильное
поведение, а не повод подставить двойника.

HTTP: `wiki_client` (владелец в `system`), `wiki_client_member` (второй
пользователь той же компании), `wiki_client_company2` (чужая компания).
Домен: `wiki_container`, `wiki_repository`, `wiki_service`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from apps.wiki.container import get_wiki_container, reset_wiki_container
from apps.wiki.models.domain import WikiPage
from core.namespace.service import NamespaceService
from tests.fixtures.auth import service_client_asgi_auth_context
from tests.fixtures.platform_events import (
    PlatformEventsReceive,
)
from tests.fixtures.platform_events import (
    platform_events_listener as open_platform_events_stream,
)

API_PREFIX = "/wiki/api/v1"
PAGES_URL = f"{API_PREFIX}/pages"

NAMESPACE_HEADER = "X-Platform-Namespace"


@pytest.fixture
def wiki_container(setup_database_before_tests):
    _ = setup_database_before_tests
    reset_wiki_container()
    container = get_wiki_container()
    container.bind_files_route_segment("wiki")
    yield container
    reset_wiki_container()


@pytest.fixture
def wiki_repository(wiki_container):
    return wiki_container.wiki_repository


@pytest.fixture
def wiki_service(wiki_container):
    return wiki_container.wiki_service


@pytest.fixture
def wiki_rag_index(wiki_container):
    return wiki_container.wiki_rag_index_service


@pytest_asyncio.fixture
async def wiki_app(rag_service):
    """ASGI-приложение сервиса.

    RAG обязателен: каждое сохранение страницы пишет её в индекс.
    """
    _ = rag_service
    from apps.wiki.main import app

    return app


@pytest_asyncio.fixture
async def wiki_namespace(wiki_container, unique_id: str) -> str:
    """Отдельное пространство на тест — граница изоляции данных."""
    service: NamespaceService = wiki_container.namespace_service
    name = f"wiki-test-{unique_id}"
    _ = await service.get_or_create(name, description=f"Wiki test namespace {unique_id}")
    return name


@pytest_asyncio.fixture
async def wiki_other_namespace(wiki_container, unique_id: str) -> str:
    """Второе пространство той же компании — для проверок изоляции."""
    service: NamespaceService = wiki_container.namespace_service
    name = f"wiki-other-{unique_id}"
    _ = await service.get_or_create(name, description=f"Wiki other namespace {unique_id}")
    return name


def _client(app: object, headers: dict[str, str], namespace: str) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={**headers, NAMESPACE_HEADER: namespace},
    )


@pytest_asyncio.fixture
async def wiki_client(wiki_app, auth_headers_system, wiki_namespace) -> AsyncIterator[AsyncClient]:
    async with _client(wiki_app, auth_headers_system, wiki_namespace) as client:
        yield client


@pytest_asyncio.fixture
async def wiki_client_member(
    wiki_app, auth_headers_system_user2, wiki_namespace
) -> AsyncIterator[AsyncClient]:
    """Второй пользователь той же компании: видит общие страницы, но не ограниченные."""
    async with _client(wiki_app, auth_headers_system_user2, wiki_namespace) as client:
        yield client


@pytest_asyncio.fixture
async def wiki_client_company2(
    wiki_app, auth_headers_company2, wiki_namespace
) -> AsyncIterator[AsyncClient]:
    """Пользователь другой компании: пространство ему не принадлежит."""
    async with _client(wiki_app, auth_headers_company2, wiki_namespace) as client:
        yield client


@pytest_asyncio.fixture
async def wiki_client_other_namespace(
    wiki_app, auth_headers_system, wiki_other_namespace
) -> AsyncIterator[AsyncClient]:
    """Тот же пользователь, другое пространство."""
    async with _client(wiki_app, auth_headers_system, wiki_other_namespace) as client:
        yield client


@pytest_asyncio.fixture
async def wiki_client_anonymous(wiki_app) -> AsyncIterator[AsyncClient]:
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
