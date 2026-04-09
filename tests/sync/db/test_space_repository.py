"""Тесты SpaceRepository."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.sync.db.models import SyncSpace
from apps.sync.db.repositories.space_repository import SpaceRepository


@pytest.mark.asyncio
async def test_space_crud(
    space_repo: SpaceRepository, sync_db_clean: None, company_id: str, unique_id: str
) -> None:
    """Полный CRUD-цикл: create, get, list, delete."""
    s1 = f"{unique_id}_space_1"
    s2 = f"{unique_id}_space_2"
    space = SyncSpace(
        space_id=s1,
        company_id=company_id,
        name="Space One",
        description="desc",
        created_at=datetime.now(tz=UTC),
        created_by_user_id="user_1",
    )
    await space_repo.create(space)

    got = await space_repo.get(s1)
    assert got is not None
    assert got.space_id == s1
    assert got.name == "Space One"
    assert got.company_id == company_id

    space_2 = SyncSpace(
        space_id=s2,
        company_id=company_id,
        name="Space Two",
        description=None,
        created_at=datetime.now(tz=UTC),
        created_by_user_id="user_2",
    )
    await space_repo.create(space_2)

    listed = await space_repo.list_all(company_id=company_id)
    assert {s.space_id for s in listed} == {s1, s2}

    deleted = await space_repo.delete(s2)
    assert deleted is True
    assert await space_repo.get(s2) is None


@pytest.mark.asyncio
async def test_space_get_by_name(
    space_repo: SpaceRepository, sync_db_clean: None, company_id: str, unique_id: str
) -> None:
    """Поиск пространства по имени внутри компании."""
    sn = f"{unique_id}_space_named"
    space = SyncSpace(
        space_id=sn,
        company_id=company_id,
        name="Unique Name",
        created_at=datetime.now(tz=UTC),
        created_by_user_id="user_1",
    )
    await space_repo.create(space)

    found = await space_repo.get_by_name("Unique Name", company_id=company_id)
    assert found is not None
    assert found.space_id == sn

    not_found = await space_repo.get_by_name("Nonexistent", company_id=company_id)
    assert not_found is None


@pytest.mark.asyncio
async def test_space_company_isolation(
    space_repo: SpaceRepository, sync_db_clean: None, unique_id: str
) -> None:
    """Пространства разных компаний не пересекаются."""
    company_a = f"{unique_id}_company_a"
    company_b = f"{unique_id}_company_b"
    space_a = SyncSpace(
        space_id=f"{unique_id}_space_a",
        company_id=company_a,
        name="Space A",
        created_at=datetime.now(tz=UTC),
        created_by_user_id="user_1",
    )
    space_b = SyncSpace(
        space_id=f"{unique_id}_space_b",
        company_id=company_b,
        name="Space B",
        created_at=datetime.now(tz=UTC),
        created_by_user_id="user_1",
    )
    await space_repo.create(space_a)
    await space_repo.create(space_b)

    list_a = await space_repo.list_all(company_id=company_a)
    assert [s.space_id for s in list_a] == [f"{unique_id}_space_a"]

    list_b = await space_repo.list_all(company_id=company_b)
    assert [s.space_id for s in list_b] == [f"{unique_id}_space_b"]


@pytest.mark.asyncio
async def test_get_by_name_same_name_different_companies(
    space_repo: SpaceRepository,
    sync_db_clean: None,
    unique_id: str,
) -> None:
    """Одинаковое имя в разных компаниях — разные записи."""
    co_x = f"{unique_id}_co_x"
    co_y = f"{unique_id}_co_y"
    sp_x = f"{unique_id}_sp_x"
    sp_y = f"{unique_id}_sp_y"
    for cid, sid in ((co_x, sp_x), (co_y, sp_y)):
        await space_repo.create(
            SyncSpace(
                space_id=sid,
                company_id=cid,
                name="SharedName",
                created_at=datetime.now(tz=UTC),
                created_by_user_id="u1",
            )
        )
    ax = await space_repo.get_by_name("SharedName", company_id=co_x)
    ay = await space_repo.get_by_name("SharedName", company_id=co_y)
    assert ax is not None and ay is not None
    assert ax.space_id == sp_x
    assert ay.space_id == sp_y
