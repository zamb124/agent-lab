"""Аудит act-as: `impersonated_by` из JWT протянут в `Context.metadata`.

Проверяем `ContextFactory` напрямую с реальным контейнером (без моков).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from starlette.requests import Request

from core.middleware.auth.context_factory import ContextFactory
from core.models.identity_models import User
from core.utils.tokens import TokenData
from tests.fixtures.ai_provider_defaults import make_test_company

pytestmark = pytest.mark.asyncio


def _request() -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"host", b"testserver")],
        "query_string": b"",
    }
    return Request(scope)


def _token_data(user_id: str, company_id: str, *, impersonated_by: str | None) -> TokenData:
    metadata = {"impersonated_by": impersonated_by} if impersonated_by else {}
    return TokenData(
        user_id=user_id,
        company_id=company_id,
        roles=["member"],
        exp=datetime.now(timezone.utc) + timedelta(hours=1),
        metadata=metadata,
    )


async def test_impersonated_by_propagated(frontend_container, unique_id):
    factory = ContextFactory(frontend_container)
    company = make_test_company(company_id="system", name="System")
    user = User(
        user_id=f"emp_{unique_id}",
        name="Emp",
        companies={"system": ["member"]},
        active_company_id="system",
    )
    td = _token_data(user.user_id, "system", impersonated_by="curator_1")

    ctx = await factory.create(
        _request(), context_type="api", company=company, user=user, token_data=td
    )
    assert ctx.metadata.get("impersonated_by") == "curator_1"


async def test_normal_token_has_no_impersonated_by(frontend_container, unique_id):
    factory = ContextFactory(frontend_container)
    company = make_test_company(company_id="system", name="System")
    user = User(
        user_id=f"human_{unique_id}",
        name="Human",
        companies={"system": ["member"]},
        active_company_id="system",
    )
    td = _token_data(user.user_id, "system", impersonated_by=None)

    ctx = await factory.create(
        _request(), context_type="api", company=company, user=user, token_data=td
    )
    assert "impersonated_by" not in ctx.metadata
