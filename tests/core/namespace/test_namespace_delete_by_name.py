"""Физическое удаление Namespace по имени внутри компании."""

from __future__ import annotations

import pytest

from core.context import clear_context, set_context
from core.models.context_models import Context
from core.models.identity_models import Company, Namespace, NamespaceKind, User, UserStatus


def _bind(company_id: str, unique_id: str) -> None:
    user = User(
        user_id=f"nsdel-{company_id}",
        name="NS",
        status=UserStatus.ACTIVE,
        companies={company_id: ["owner"]},
        active_company_id=company_id,
    )
    company = Company(
        company_id=company_id,
        name=company_id,
        subdomain=f"nsd{unique_id}{company_id}"[:32],
        owner_user_id=user.user_id,
    )
    _ = set_context(
        Context(
            user=user,
            active_company=company,
            user_companies=[company],
            channel="test",
        )
    )


@pytest.mark.asyncio
async def test_delete_by_name_stays_inside_company(unique_id: str) -> None:
    company_id = f"nsa_{unique_id}"
    other_company_id = f"nsb_{unique_id}"
    name = f"sales_{unique_id}"
    _bind(company_id, unique_id)
    try:
        row = Namespace(
            namespace_id=f"{company_id}:{name}",
            name=name,
            company_id=company_id,
        )
        assert await Namespace.set(row) is True
        _bind(other_company_id, unique_id)
        assert await Namespace.by_name(name) is None
        assert await Namespace.delete_by_name(name) is False
        _bind(company_id, unique_id)
        assert await Namespace.by_name(name) is not None
        assert await Namespace.delete_by_name(name) is True
        assert await Namespace.delete_by_name(name) is False
        assert await Namespace.by_name(name) is None
        assert await Namespace.delete_by_name(f"missing_{unique_id}") is False
    finally:
        clear_context()


async def _put(company_id: str, name: str, kind: NamespaceKind) -> None:
    row = Namespace(
        namespace_id=f"{company_id}:{name}",
        name=name,
        company_id=company_id,
        kind=kind,
    )
    assert await Namespace.set(row) is True


@pytest.mark.asyncio
async def test_list_by_kind_orders_and_pages(unique_id: str) -> None:
    company_id = f"nsl_{unique_id}"
    other_company_id = f"nso_{unique_id}"
    _bind(company_id, unique_id)
    try:
        await _put(company_id, f"beta_{unique_id}", NamespaceKind.COMPANY_WORKSPACE)
        await _put(company_id, f"alpha_{unique_id}", NamespaceKind.COMPANY_WORKSPACE)
        await _put(company_id, f"office-catalog-{unique_id}", NamespaceKind.TECHNICAL)
        workspaces = await Namespace.list_for_kinds_by_name_asc(
            [NamespaceKind.COMPANY_WORKSPACE],
            limit=10,
            offset=0,
        )
        names = [row.name for row in workspaces]
        assert names == [f"alpha_{unique_id}", f"beta_{unique_id}"]
        page = await Namespace.list_for_kinds_by_name_asc(
            [NamespaceKind.COMPANY_WORKSPACE],
            limit=1,
            offset=1,
        )
        assert [row.name for row in page] == [f"beta_{unique_id}"]
        assert await Namespace.count_by_kind([NamespaceKind.COMPANY_WORKSPACE]) == 2
        assert await Namespace.count_by_kind([NamespaceKind.TECHNICAL]) == 1
        assert await Namespace.list_for_kinds_by_name_asc([], limit=10, offset=0) == []
        assert await Namespace.count_by_kind([]) == 0
        _bind(other_company_id, unique_id)
        assert await Namespace.list_for_kinds_by_name_asc(
            [NamespaceKind.COMPANY_WORKSPACE],
            limit=10,
            offset=0,
        ) == []
        _bind(company_id, unique_id)
        for item_name in (
            f"alpha_{unique_id}",
            f"beta_{unique_id}",
            f"office-catalog-{unique_id}",
        ):
            assert await Namespace.delete_by_name(item_name) is True
    finally:
        clear_context()
