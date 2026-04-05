"""Контекст компании для execute_command (is_member через get_context)."""

from __future__ import annotations

import pytest
import pytest_asyncio

from core.context import clear_context, set_context
from core.models.context_models import Context
from core.models.i18n_models import Language
from core.models.identity_models import Company, User


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
