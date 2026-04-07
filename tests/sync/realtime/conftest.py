"""Контекст компании для execute_command (is_member через get_context)."""

from __future__ import annotations

import pytest
import pytest_asyncio

from apps.sync.container import get_sync_container
from core.billing import set_billing_service
from core.context import clear_context, set_context
from core.models.context_models import Context
from core.models.i18n_models import Language
from core.models.identity_models import Company, User


@pytest_asyncio.fixture(autouse=True)
async def _ensure_billing_company_for_realtime(
    company_id: str,
    sync_db_clean: None,
) -> None:
    """LiveKit create_room вызывает billing: компания должна быть в shared-хранилище."""
    container = get_sync_container()
    set_billing_service(container.billing_service)
    await container.company_repository.set(
        Company(
            company_id=company_id,
            name=company_id,
            owner_user_id="u1",
            members={"u1": ["owner"], "member1": ["member"], "u_other": ["member"]},
            balance=1000.0,
        )
    )


@pytest.fixture(autouse=True)
def _handler_company_context(company_id: str) -> None:
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
