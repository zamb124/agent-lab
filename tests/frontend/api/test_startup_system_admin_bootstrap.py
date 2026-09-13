from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from core.authz.service import AuthzService
from core.identity.system_bootstrap import (
    SYSTEM_ADMIN_EMAIL,
    ensure_system_admin_membership,
    ensure_system_company_exists,
    load_system_admin_membership,
)
from core.models.identity_models import Company, User
from tests.fixtures.auth import set_test_company_member_roles  # noqa: F401


def _fake_authz() -> AuthzService:
    authz = AsyncMock(spec=AuthzService)
    authz.write_and_delete = AsyncMock()
    return authz


class _InMemoryRepo:
    def __init__(self, entities: dict[str, object], entity_id_field: str):
        self._entities = entities
        self._entity_id_field = entity_id_field

    async def get(self, entity_id: str):
        return self._entities.get(entity_id)

    async def set(self, entity):
        entity_id = getattr(entity, self._entity_id_field)
        self._entities[entity_id] = entity
        return True

    async def list(self, *, limit: int, offset: int = 0):
        items = list(self._entities.values())
        return items[offset:offset + limit]

    async def find_all_by_email_ci(self, email: str):
        norm = email.strip().lower()
        if not norm:
            raise ValueError("email для поиска не может быть пустым")
        matched: list[User] = []
        for entity in self._entities.values():
            if not isinstance(entity, User):
                raise TypeError("find_all_by_email_ci requires User entities")
            if any(item.strip().lower() == norm for item in entity.emails):
                matched.append(entity)
        return matched


class _InMemorySubdomainRepo:
    def __init__(self):
        self._mapping: dict[str, str] = {}

    async def set_mapping(self, subdomain: str, company_id: str):
        self._mapping[subdomain] = company_id
        return True

    async def get_company_id(self, subdomain: str):
        return self._mapping.get(subdomain)


class _Container:
    def __init__(self, company_repo: _InMemoryRepo, user_repo: _InMemoryRepo):
        self.company_repository = company_repo
        self.user_repository = user_repo
        self.subdomain_repository = _InMemorySubdomainRepo()


@pytest.mark.asyncio
async def test_bootstrap_adds_admin_role_to_system_company_and_user():
    company = Company(company_id="system", name="System", members={})
    user = User(
        user_id="user-1",
        name="Viktor",
        emails=["zambas124@yandex.ru"],
        companies={"system": ["viewer"]},
    )
    container = _Container(
        company_repo=_InMemoryRepo({"system": company}, "company_id"),
        user_repo=_InMemoryRepo({"user-1": user}, "user_id"),
    )
    authz = _fake_authz()

    await ensure_system_admin_membership(
        company_repository=container.company_repository,
        subdomain_repository=container.subdomain_repository,
        user_repository=container.user_repository,
        authz=authz,
    )

    assert "admin" in container.company_repository._entities["system"].members["user-1"]
    assert "admin" in container.user_repository._entities["user-1"].companies["system"]
    authz.write_and_delete.assert_awaited()


@pytest.mark.asyncio
async def test_bootstrap_skips_admin_when_target_email_user_missing():
    company = Company(company_id="system", name="System", members={})
    other_user = User(user_id="user-2", name="Other", emails=["other@example.com"], companies={})
    container = _Container(
        company_repo=_InMemoryRepo({"system": company}, "company_id"),
        user_repo=_InMemoryRepo({"user-2": other_user}, "user_id"),
    )

    returned_company, returned_user = await ensure_system_admin_membership(
        company_repository=container.company_repository,
        subdomain_repository=container.subdomain_repository,
        user_repository=container.user_repository,
        authz=_fake_authz(),
    )

    assert returned_company.company_id == "system"
    assert returned_user is None
    assert "user-2" not in container.company_repository._entities["system"].members


@pytest.mark.asyncio
async def test_bootstrap_creates_system_company_when_missing():
    user = User(
        user_id="user-3",
        name="Viktor",
        emails=["zambas124@yandex.ru"],
        companies={},
    )
    container = _Container(
        company_repo=_InMemoryRepo({}, "company_id"),
        user_repo=_InMemoryRepo({"user-3": user}, "user_id"),
    )

    company = await ensure_system_company_exists(
        company_repository=container.company_repository,
        subdomain_repository=container.subdomain_repository,
    )

    assert company.company_id == "system"
    assert company.subdomain == "system"
    assert "system" in container.company_repository._entities
    assert await container.subdomain_repository.get_company_id("system") == "system"


@pytest.mark.asyncio
async def test_bootstrap_skips_fga_write_when_already_admin():
    company = Company(company_id="system", name="System", members={"user-1": ["admin"]})
    user = User(
        user_id="user-1",
        name="Viktor",
        emails=[SYSTEM_ADMIN_EMAIL],
        companies={"system": ["admin"]},
    )
    container = _Container(
        company_repo=_InMemoryRepo({"system": company}, "company_id"),
        user_repo=_InMemoryRepo({"user-1": user}, "user_id"),
    )
    authz = _fake_authz()

    returned_company, returned_user = await ensure_system_admin_membership(
        company_repository=container.company_repository,
        subdomain_repository=container.subdomain_repository,
        user_repository=container.user_repository,
        authz=authz,
    )

    assert returned_company.company_id == "system"
    assert returned_user is not None
    assert returned_user.user_id == "user-1"
    authz.write_and_delete.assert_not_called()


def _load_repos(*, company: Company | None, users: dict[str, User]) -> tuple[_InMemoryRepo, _InMemoryRepo]:
    companies: dict[str, object] = {}
    if company is not None:
        companies[company.company_id] = company
    return _InMemoryRepo(companies, "company_id"), _InMemoryRepo(users, "user_id")


@pytest.mark.asyncio
async def test_load_system_admin_membership_returns_existing_admin():
    company = Company(company_id="system", name="System", members={"user-1": ["admin"]})
    user = User(
        user_id="user-1",
        name="Viktor",
        emails=[SYSTEM_ADMIN_EMAIL],
        companies={"system": ["admin"]},
    )
    company_repo, user_repo = _load_repos(company=company, users={"user-1": user})

    loaded_company, loaded_user = await load_system_admin_membership(
        company_repository=company_repo,
        user_repository=user_repo,
    )

    assert loaded_company.company_id == "system"
    assert loaded_user.user_id == "user-1"


@pytest.mark.asyncio
async def test_load_system_admin_membership_requires_system_company():
    user = User(
        user_id="user-1",
        name="Viktor",
        emails=[SYSTEM_ADMIN_EMAIL],
        companies={"system": ["admin"]},
    )
    company_repo, user_repo = _load_repos(company=None, users={"user-1": user})

    with pytest.raises(ValueError, match="system company is required"):
        await load_system_admin_membership(
            company_repository=company_repo,
            user_repository=user_repo,
        )


@pytest.mark.asyncio
async def test_load_system_admin_membership_requires_admin_user():
    company = Company(company_id="system", name="System", members={})
    other = User(user_id="user-2", name="Other", emails=["other@example.com"], companies={})
    company_repo, user_repo = _load_repos(company=company, users={"user-2": other})

    with pytest.raises(ValueError, match="system admin user"):
        await load_system_admin_membership(
            company_repository=company_repo,
            user_repository=user_repo,
        )


@pytest.mark.asyncio
async def test_load_system_admin_membership_requires_admin_role():
    company = Company(company_id="system", name="System", members={"user-1": ["viewer"]})
    user = User(
        user_id="user-1",
        name="Viktor",
        emails=[SYSTEM_ADMIN_EMAIL],
        companies={"system": ["viewer"]},
    )
    company_repo, user_repo = _load_repos(company=company, users={"user-1": user})

    with pytest.raises(ValueError, match="system admin roster missing admin role"):
        await load_system_admin_membership(
            company_repository=company_repo,
            user_repository=user_repo,
        )


@pytest.mark.asyncio
async def test_load_system_admin_membership_rejects_duplicate_email():
    company = Company(
        company_id="system",
        name="System",
        members={"user-1": ["admin"], "user-2": ["admin"]},
    )
    user_one = User(
        user_id="user-1",
        name="Viktor",
        emails=[SYSTEM_ADMIN_EMAIL],
        companies={"system": ["admin"]},
    )
    user_two = User(
        user_id="user-2",
        name="Viktor-2",
        emails=[SYSTEM_ADMIN_EMAIL.upper()],
        companies={"system": ["admin"]},
    )
    company_repo, user_repo = _load_repos(
        company=company,
        users={"user-1": user_one, "user-2": user_two},
    )

    with pytest.raises(ValueError, match="Multiple users found"):
        await load_system_admin_membership(
            company_repository=company_repo,
            user_repository=user_repo,
        )
