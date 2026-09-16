"""
Фикстуры для авторизации в тестах CRM и E2E UI.

Две компании (`system`, `company2`), четыре пользователя с ролями owner/admin и member.
Для браузера (pytest Playwright): см. tests/ui/conftest.py — `ui_page_system`, `ui_page_system_member`,
`ui_page_company2`, `ui_page_company2_member`, `page` / `ui_page_anonymous` без cookie.

Токены:
1. auth_token_system / auth_headers_system — system, owner+admin
2. auth_token_system_user2 / auth_headers_system_user2 — system, member
3. auth_token_company2 / auth_headers_company2 — company2, owner+admin
4. auth_token_company2_user2 / auth_headers_company2_user2 — company2, member

Membership roster пишется в shared storage и dual-write в OpenFGA
(`sync_company_member_roles`) — PDP/broadcast читают только FGA.
"""

import uuid
from collections.abc import Sequence
from contextlib import contextmanager

import pytest_asyncio

from core.authz.company_sync import sync_company_member_roles
from core.authz.group_sync import sync_user_groups
from core.authz.service import AuthzService
from core.config.models import OpenFGAConfig
from core.context import clear_context, set_context
from core.db.repositories.company_repository import CompanyRepository
from core.models.context_models import Context
from core.models.identity_models import User
from core.utils.tokens import get_token_service
from tests.fixtures.ai_provider_defaults import (
    company_with_test_ai_provider_defaults,
    make_test_company,
)

_TEST_ADMIN_GROUPS: tuple[str, ...] = ("admin", "developers")


async def _sync_test_company_membership(
    authz: AuthzService,
    *,
    company_id: str,
    user_id: str,
    roles: Sequence[str],
) -> None:
    await sync_company_member_roles(
        authz,
        company_id=company_id,
        user_id=user_id,
        roles=roles,
    )


async def _sync_test_admin_groups(
    authz: AuthzService, *, user_id: str, company_ids: Sequence[str]
) -> None:
    """Platform groups for group-locked flows (example_react permission admin/developers)."""
    await sync_user_groups(
        authz,
        user_id=user_id,
        groups=_TEST_ADMIN_GROUPS,
        company_ids=company_ids,
        previous_groups=[],
    )


async def set_test_company_member_roles(
    company_repository: CompanyRepository,
    authz: AuthzService,
    *,
    company_id: str,
    user_id: str,
    roles: Sequence[str],
) -> None:
    """Roster + OpenFGA dual-write for test membership mutations."""
    _ = await company_repository.put_member_roles(company_id, user_id, roles)
    await _sync_test_company_membership(
        authz,
        company_id=company_id,
        user_id=user_id,
        roles=roles,
    )


@pytest_asyncio.fixture(scope="session", autouse=True)
async def ensure_default_test_user_authz(openfga_settings: OpenFGAConfig) -> None:
    """Dual-write FGA для in-process test_user/system и startup user:system."""
    from core.authz.factory import build_authz_service

    authz = build_authz_service(openfga_settings)
    for user_id, roles in (
        ("test_user", ["owner", "admin"]),
        ("test-user", ["owner", "admin"]),
        ("system", ["owner", "admin"]),
        ("seed_owner", ["owner", "admin"]),
    ):
        await _sync_test_company_membership(
            authz,
            company_id="system",
            user_id=user_id,
            roles=roles,
        )
        await _sync_test_admin_groups(authz, user_id=user_id, company_ids=["system"])


@pytest_asyncio.fixture(scope="session")
async def auth_token_system(frontend_container, openfga_settings: OpenFGAConfig):
    """
    Создает основного пользователя с компанией "system" для всей сессии тестов.

    scope="session" - токен создается один раз на все тесты.
    """
    _ = openfga_settings
    user_id = f"test_user_system_{uuid.uuid4().hex[:8]}"
    company_id = "system"
    company_roles = ["owner", "admin"]

    # Создаем или получаем компанию system
    existing_company = await frontend_container.company_repository.get(company_id)
    if not existing_company:
        company = make_test_company(
            company_id=company_id,
            name="System Company",
            owner_user_id=user_id,
            members={user_id: company_roles},
        )
        await frontend_container.company_repository.set(company)
        await frontend_container.subdomain_repository.set_mapping("system", company_id)
    else:
        existing_company = company_with_test_ai_provider_defaults(existing_company)
        if user_id not in existing_company.members:
            existing_company.members[user_id] = company_roles
        await frontend_container.company_repository.set(existing_company)

    # Создаем пользователя
    user = User(
        user_id=user_id,
        name="System User 1",
        emails=[f"{user_id}@system.com"],
        companies={company_id: company_roles},
        active_company_id=company_id
    )
    await frontend_container.user_repository.set(user)
    await _sync_test_company_membership(
        frontend_container.authz_service,
        company_id=company_id,
        user_id=user_id,
        roles=company_roles,
    )
    await _sync_test_admin_groups(
        frontend_container.authz_service, user_id=user_id, company_ids=[company_id]
    )

    token_service = get_token_service()
    token = token_service.create_token(user_id, company_id=company_id, roles=company_roles)

    yield token


@pytest_asyncio.fixture
async def system_user_id(auth_token_system):
    """
    Возвращает user_id основного пользователя системной компании.
    """
    token_service = get_token_service()
    token_data = token_service.validate_token(auth_token_system)
    if not token_data:
        raise ValueError("Invalid token")
    return token_data.user_id


@pytest_asyncio.fixture
async def auth_headers_system(auth_token_system):
    """
    Заголовки для основного пользователя системной компании.

    Пример:
        async def test_something(crm_client, auth_headers_system):
            response = await crm_client.get("/crm/api/v1/entities/", headers=auth_headers_system)
    """
    return {"Authorization": f"Bearer {auth_token_system}"}


@pytest_asyncio.fixture
async def ws_cookie_system(auth_token_system, system_user_id):
    """
    Cookie для WebSocket подключения системного пользователя.

    Пример:
        async with websockets.connect(ws_url, additional_headers=ws_cookie_system) as ws:
            ...
    """
    # Для WebSocket используем auth_token как session_id
    # В тестах auth middleware извлекает user из токена
    return {"Cookie": f"auth_token={auth_token_system}; session_id={system_user_id}"}


@pytest_asyncio.fixture(scope="session")
async def auth_token_system_user2(frontend_container, openfga_settings: OpenFGAConfig):
    """
    Создает второго пользователя в компании "system" для всей сессии тестов.
    Используется для проверки доступа между пользователями одной компании.
    """
    _ = openfga_settings
    user_id = f"test_user_system2_{uuid.uuid4().hex[:8]}"
    company_id = "system"
    company_roles = ["member"]

    # Компания system уже должна существовать (создана в auth_token_system)
    existing_company = await frontend_container.company_repository.get(company_id)
    if existing_company:
        existing_company = company_with_test_ai_provider_defaults(existing_company)
        if user_id not in existing_company.members:
            existing_company.members[user_id] = company_roles
        await frontend_container.company_repository.set(existing_company)
    else:
        # Если почему-то не существует - создаем
        company = make_test_company(
            company_id=company_id,
            name="System Company",
            owner_user_id=user_id,
            members={user_id: company_roles},
        )
        await frontend_container.company_repository.set(company)

    # Создаем второго пользователя
    user = User(
        user_id=user_id,
        name="System User 2",
        emails=[f"{user_id}@system.com"],
        companies={company_id: company_roles},
        active_company_id=company_id
    )
    await frontend_container.user_repository.set(user)
    await _sync_test_company_membership(
        frontend_container.authz_service,
        company_id=company_id,
        user_id=user_id,
        roles=company_roles,
    )

    token_service = get_token_service()
    token = token_service.create_token(user_id, company_id=company_id)

    yield token


@pytest_asyncio.fixture
async def auth_headers_system_user2(auth_token_system_user2):
    """
    Заголовки для второго пользователя системной компании.

    Пример:
        async def test_same_company_access(crm_client, auth_headers_system, auth_headers_system_user2):
            # Создаем entity как user1
            resp1 = await crm_client.post("/crm/api/v1/entities/", json={...}, headers=auth_headers_system)
            entity_id = resp1.json()["entity_id"]

            # Проверяем доступ как user2 из той же компании
            resp2 = await crm_client.get(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_system_user2)
    """
    return {"Authorization": f"Bearer {auth_token_system_user2}"}


@pytest_asyncio.fixture
async def system_user2_id(auth_token_system_user2):
    token_service = get_token_service()
    token_data = token_service.validate_token(auth_token_system_user2)
    if not token_data:
        raise ValueError("Invalid token")
    return token_data.user_id


@pytest_asyncio.fixture
async def ws_cookie_system_user2(auth_token_system_user2, system_user2_id):
    return {"Cookie": f"auth_token={auth_token_system_user2}; session_id={system_user2_id}"}


@pytest_asyncio.fixture(scope="session")
async def auth_token_company2(frontend_container, openfga_settings: OpenFGAConfig):
    """
    Создает пользователя из другой компании (company2) для всей сессии тестов.
    Используется для проверки cross-company доступа.
    """
    _ = openfga_settings
    user_id = f"test_user_company2_{uuid.uuid4().hex[:8]}"
    company_id = "company2"
    company_roles = ["owner", "admin"]

    # Создаем компанию company2
    existing_company = await frontend_container.company_repository.get(company_id)
    if not existing_company:
        company = make_test_company(
            company_id=company_id,
            name="Company 2",
            owner_user_id=user_id,
            members={user_id: company_roles},
        )
        await frontend_container.company_repository.set(company)
        await frontend_container.subdomain_repository.set_mapping("company2", company_id)
    else:
        existing_company = company_with_test_ai_provider_defaults(existing_company)
        if user_id not in existing_company.members:
            existing_company.members[user_id] = company_roles
        await frontend_container.company_repository.set(existing_company)

    # Создаем пользователя
    user = User(
        user_id=user_id,
        name="Company2 User 1",
        emails=[f"{user_id}@company2.com"],
        companies={company_id: company_roles},
        active_company_id=company_id
    )
    await frontend_container.user_repository.set(user)
    await _sync_test_company_membership(
        frontend_container.authz_service,
        company_id=company_id,
        user_id=user_id,
        roles=company_roles,
    )
    await _sync_test_admin_groups(
        frontend_container.authz_service, user_id=user_id, company_ids=[company_id]
    )

    token_service = get_token_service()
    token = token_service.create_token(user_id, company_id=company_id)

    yield token


@pytest_asyncio.fixture
async def auth_headers_company2(auth_token_company2):
    """
    Заголовки для пользователя из другой компании (company2).

    Пример:
        async def test_cross_company_access(crm_client, auth_headers_system, auth_headers_company2):
            # Создаем public entity как system user
            resp1 = await crm_client.post("/crm/api/v1/entities/", json={...}, headers=auth_headers_system)
            entity_id = resp1.json()["entity_id"]

            # Делаем public
            await crm_client.post(f"/crm/api/v1/entity-grants/{entity_id}/public", headers=auth_headers_system)

            # Проверяем доступ как user из company2
            resp2 = await crm_client.get(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_company2)
    """
    return {"Authorization": f"Bearer {auth_token_company2}"}


@pytest_asyncio.fixture(scope="session")
async def auth_token_company2_user2(frontend_container, openfga_settings: OpenFGAConfig):
    """
    Создает второго пользователя в компании company2 для всей сессии тестов.
    Используется для проверки доступа между пользователями другой компании.
    """
    _ = openfga_settings
    user_id = f"test_user_company2_u2_{uuid.uuid4().hex[:8]}"
    company_id = "company2"
    company_roles = ["member"]

    # Компания company2 уже должна существовать (создана в auth_token_company2)
    existing_company = await frontend_container.company_repository.get(company_id)
    if existing_company:
        existing_company = company_with_test_ai_provider_defaults(existing_company)
        if user_id not in existing_company.members:
            existing_company.members[user_id] = company_roles
        await frontend_container.company_repository.set(existing_company)
    else:
        # Если почему-то не существует - создаем
        company = make_test_company(
            company_id=company_id,
            name="Company 2",
            owner_user_id=user_id,
            members={user_id: company_roles},
        )
        await frontend_container.company_repository.set(company)

    # Создаем второго пользователя
    user = User(
        user_id=user_id,
        name="Company2 User 2",
        emails=[f"{user_id}@company2.com"],
        companies={company_id: company_roles},
        active_company_id=company_id
    )
    await frontend_container.user_repository.set(user)
    await _sync_test_company_membership(
        frontend_container.authz_service,
        company_id=company_id,
        user_id=user_id,
        roles=company_roles,
    )

    token_service = get_token_service()
    token = token_service.create_token(user_id, company_id=company_id)

    yield token


@pytest_asyncio.fixture
async def auth_headers_company2_user2(auth_token_company2_user2):
    """
    Заголовки для второго пользователя из компании company2.

    Пример:
        async def test_company2_internal_access(crm_client, auth_headers_company2, auth_headers_company2_user2):
            # Создаем entity как company2 user1
            resp1 = await crm_client.post("/crm/api/v1/entities/", json={...}, headers=auth_headers_company2)
            entity_id = resp1.json()["entity_id"]

            # Проверяем доступ как company2 user2
            resp2 = await crm_client.get(f"/crm/api/v1/entities/{entity_id}", headers=auth_headers_company2_user2)
    """
    return {"Authorization": f"Bearer {auth_token_company2_user2}"}


@pytest_asyncio.fixture(scope="session")
async def test_company_subdomains_initialized(
    frontend_container,
    auth_token_system,
    auth_token_company2,
) -> None:
    """Subdomain + SubdomainRepository для system/company2 (Host routing в agent E2E)."""
    _ = auth_token_system
    _ = auth_token_company2

    async def ensure_company_subdomain(company_id: str, slug: str) -> None:
        company = await frontend_container.company_repository.get(company_id)
        if company is None:
            raise ValueError(
                f"Компания {company_id} не найдена — сначала фикстуры auth_token_*"
            )
        if company.subdomain != slug:
            company.subdomain = slug
            await frontend_container.company_repository.set(company)
        await frontend_container.subdomain_repository.set_mapping(slug, company_id)

    await ensure_company_subdomain("system", "system")
    # UI E2E overrides auth_token_company2 → ui_e2e_*_c2. Agent desktop E2E still
    # expects literal company_id/subdomain "company2" for Host routing.
    company2 = await frontend_container.company_repository.get("company2")
    if company2 is None:
        owner_id = "test_company2_owner"
        company2 = make_test_company(
            company_id="company2",
            name="Company 2",
            owner_user_id=owner_id,
            members={owner_id: ["owner", "admin"]},
            subdomain="company2",
        )
        await frontend_container.company_repository.set(company2)
    await ensure_company_subdomain("company2", "company2")


@contextmanager
def service_client_asgi_auth_context(auth_headers: dict[str, str]):
    """
    Контекст с auth_token для ServiceClient при ASGI-вызовах другого сервиса (например flows → rag).
    """
    raw = auth_headers["Authorization"].replace("Bearer ", "").strip()
    token_data = get_token_service().validate_token(raw)
    if token_data is None:
        raise ValueError("Невалидный токен в service_client_asgi_auth_context")
    company_id = token_data.company_id
    if not company_id:
        raise ValueError("В токене нет company_id")
    set_context(
        Context(
            user=User(user_id=token_data.user_id, name="test"),
            active_company=make_test_company(company_id=company_id, name="test"),
            channel="test",
            session_id="test",
            auth_token=raw,
        )
    )
    try:
        yield
    finally:
        clear_context()
