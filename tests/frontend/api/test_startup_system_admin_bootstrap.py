from __future__ import annotations

import pytest

from apps.frontend.main import _ensure_system_admin_membership
from core.models.identity_models import Company, User


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

    async def list_all(self, limit: int = 100):
        return list(self._entities.values())[:limit]


class _Container:
    def __init__(self, company_repo: _InMemoryRepo, user_repo: _InMemoryRepo):
        self.company_repository = company_repo
        self.user_repository = user_repo


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

    await _ensure_system_admin_membership(container)

    assert "admin" in container.company_repository._entities["system"].members["user-1"]
    assert "admin" in container.user_repository._entities["user-1"].companies["system"]


@pytest.mark.asyncio
async def test_bootstrap_raises_if_target_email_user_missing():
    company = Company(company_id="system", name="System", members={})
    other_user = User(user_id="user-2", name="Other", emails=["other@example.com"], companies={})
    container = _Container(
        company_repo=_InMemoryRepo({"system": company}, "company_id"),
        user_repo=_InMemoryRepo({"user-2": other_user}, "user_id"),
    )

    with pytest.raises(ValueError, match="zambas124@yandex.ru"):
        await _ensure_system_admin_membership(container)
