"""Поведение auth в CRM worker tasks daily summary."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pytest import MonkeyPatch

from core.models.identity_models import Company, User

pytestmark = pytest.mark.no_crm_http


@pytest.mark.asyncio
async def test_build_auth_token_ignores_crm_worker_placeholder(
    app,
    unique_id: str,
    monkeypatch: MonkeyPatch,
) -> None:
    _ = app
    import apps.crm_worker.tasks.crm_context as crm_context

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

    authz = AsyncMock()

    captured: list[dict[str, object]] = []

    def create_token(**kwargs: object) -> str:
        captured.append(dict(kwargs))
        return "jwt-test"

    monkeypatch.setattr(crm_context, "get_token_service", lambda: SimpleNamespace(create_token=create_token))

    out = await crm_context.build_auth_token_for_company(company_id, "crm-worker", authz=authz)
    assert out == "jwt-test"
    assert len(captured) == 1
    assert captured[0]["user_id"] == owner_id
    assert captured[0]["company_id"] == company_id
