"""E2E: namespace_personal_backfill создаёт missing personal ns."""

from __future__ import annotations

import pytest

from apps.idle_worker.container import reset_container, set_container
from apps.idle_worker.tasks.namespace_personal_backfill_tasks import (
    namespace_personal_backfill,
)
from core.context import clear_context, set_context
from core.models.context_models import Context
from core.models.identity_models import Company, NamespaceKind, User, UserStatus
from core.namespace import personal_namespace_name


@pytest.fixture(autouse=True)
def _bind_idle_container(frontend_container):
    set_container(frontend_container)
    yield
    reset_container()


@pytest.mark.asyncio
async def test_namespace_personal_backfill_creates_missing_personal(
    frontend_container,
    unique_id: str,
) -> None:
    company_id = f"bfco_{unique_id}"
    user_id = f"bfu_{unique_id}"
    display = f"Backfill User {unique_id}"
    user = User(
        user_id=user_id,
        name=display,
        status=UserStatus.ACTIVE,
        emails=[f"{user_id}@t.local"],
        companies={company_id: ["member"]},
        active_company_id=company_id,
    )
    company = Company(
        company_id=company_id,
        name=f"Backfill Co {unique_id}",
        subdomain=f"bf{unique_id}"[:32],
        owner_user_id=user_id,
        members={user_id: ["member"]},
    )
    await frontend_container.user_repository.set(user)
    await frontend_container.company_repository.set(company)

    set_context(
        Context(
            user=user,
            active_company=company,
            user_companies=[company],
            channel="test",
        )
    )
    try:
        before = await frontend_container.namespace_service.get(
            personal_namespace_name(user_id)
        )
        assert before is None
    finally:
        clear_context()

    result = await namespace_personal_backfill()
    assert result["ensured"] >= 1
    assert result["companies"] >= 1

    set_context(
        Context(
            user=user,
            active_company=company,
            user_companies=[company],
            channel="test",
        )
    )
    try:
        personal = await frontend_container.namespace_service.get(
            personal_namespace_name(user_id)
        )
        assert personal is not None
        assert personal.kind == NamespaceKind.PERSONAL
        assert personal.owner_user_id == user_id
        assert personal.description == display
    finally:
        clear_context()
