"""Контекст компании для op_* (membership и `resolve_company_id` через `get_context`)."""

from __future__ import annotations

from collections.abc import Generator

import pytest
import pytest_asyncio

from apps.sync.container import get_sync_container
from apps.sync.db.base import SyncDatabase
from core.context import clear_context, set_context
from core.models.context_models import Context
from core.models.i18n_models import Language
from core.models.identity_models import Company, User


@pytest_asyncio.fixture(autouse=True)
async def _ensure_company_for_realtime(
    company_id: str,
    sync_database: SyncDatabase,
    sync_user_id: str,
) -> None:
    """Компания в shared-хранилище для биллинга (баланс) и membership-проверок в хендлерах."""
    container = get_sync_container()
    members: dict[str, list[str]] = {
        "u1": ["owner"],
        "member1": ["member"],
        "u_other": ["member"],
        sync_user_id: ["owner", "admin"],
    }
    await container.company_repository.set(
        Company(
            company_id=company_id,
            name=company_id,
            owner_user_id="u1",
            members=members,
            balance=1000.0,
        )
    )


@pytest.fixture(autouse=True)
def _handler_company_context(company_id: str) -> Generator[None, None, None]:
    company = Company(
        company_id=company_id,
        name="Test company",
        members={"u1": ["owner"], "member1": ["member"], "u_other": ["member"]},
    )
    user = User(
        user_id="u1",
        name="U1",
        companies={company_id: ["owner"]},
        active_company_id=company_id,
    )
    set_context(
        Context(
            user=user,
            active_company=company,
            user_companies=[company],
            channel="test",
            language=Language.RU,
        )
    )
    yield
    clear_context()
