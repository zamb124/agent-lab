"""Поведение auth в CRM worker tasks daily summary."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.no_crm_http


@pytest.mark.asyncio
async def test_build_auth_token_ignores_crm_worker_placeholder(monkeypatch):
    import apps.crm_worker.tasks.daily_summary_tasks as dst

    company = SimpleNamespace(owner_user_id="owner-1", members=None)
    user = SimpleNamespace(companies={"comp-x": ["member"]})

    class Container:
        company_repository = SimpleNamespace(get=AsyncMock(return_value=company))
        user_repository = SimpleNamespace(get=AsyncMock(return_value=user))

    monkeypatch.setattr(dst, "get_crm_container", lambda: Container())

    captured: list[dict] = []

    def create_token(**kwargs):
        captured.append(dict(kwargs))
        return "jwt-test"

    monkeypatch.setattr(dst, "get_token_service", lambda: SimpleNamespace(create_token=create_token))

    out = await dst._build_auth_token_for_company("comp-x", "crm-worker")
    assert out == "jwt-test"
    assert len(captured) == 1
    assert captured[0]["user_id"] == "owner-1"
    assert captured[0]["company_id"] == "comp-x"
