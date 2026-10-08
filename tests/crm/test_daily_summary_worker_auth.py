"""Поведение auth в CRM worker tasks daily summary."""

from __future__ import annotations

import pytest

from apps.crm_worker.di import CrmWorkerDi
from apps.crm_worker.tasks.crm_context import build_auth_token_for_company
from core.models.identity_models import Company, User
from core.utils.tokens import TokenType, get_token_service

pytestmark = pytest.mark.no_crm_http


@pytest.mark.asyncio
async def test_build_auth_token_ignores_crm_worker_placeholder(
    crm_worker_di: CrmWorkerDi,
    unique_id: str,
) -> None:
    company_id = f"comp_{unique_id}"
    owner_id = f"owner_{unique_id}"
    _ = await User.set(
        User(
            user_id=owner_id,
            name="Owner",
            companies={company_id: ["member"]},
        )
    )
    _ = await Company.set(
        Company(
            company_id=company_id,
            name="Daily",
            owner_user_id=owner_id,
        )
    )

    out = await build_auth_token_for_company(
        company_id,
        "crm-worker",
        authz=crm_worker_di.authz_service,
    )
    token_data = get_token_service().validate_token(out)
    assert token_data is not None
    assert token_data.user_id == owner_id
    assert token_data.company_id == company_id
    assert token_data.token_type is TokenType.SESSION
    assert token_data.roles == ["member"]
