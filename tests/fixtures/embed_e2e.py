"""Подготовка изолированной компании, пользователя и code-агента для E2E embed (поток A2A)."""

from __future__ import annotations

import pytest_asyncio

from core.context import Context, clear_context, set_context
from core.models.identity_models import Company, User
from core.utils.tokens import get_token_service


@pytest_asyncio.fixture
async def embed_test_auth(frontend_di, di, unique_id):
    from apps.flows.src.models.flow_config import Edge, FlowConfig

    company_id = f"test_company_{unique_id}"
    company = Company(
        company_id=company_id,
        name="Test Company",
        owner_user_id="test_user",
    )
    await Company.set(company)

    user_id = f"test_user_{unique_id}"
    user = User(
        user_id=user_id,
        name="Test User",
        emails=[f"{user_id}@test.com"],
        companies={company_id: ["admin"]},
        active_company_id=company_id,
    )
    await User.set(user)
    from tests.fixtures.auth import set_test_company_member_roles

    await set_test_company_member_roles(
        frontend_di.authz_service,
        company_id=company_id,
        user_id=user_id,
        roles=["admin"],
    )

    set_context(
        Context(
            user=User(user_id=user_id, name="Test"),
            active_company=Company(company_id=company_id, name="Test Company"),
            session_id="test",
            channel="test",
        )
    )
    flow_id = f"test_agent_{unique_id}"
    agent = FlowConfig(
        flow_id=flow_id,
        name="Test Agent",
        entry="main",
        nodes={
            "main": {
                "type": "code",
                "code": (
                    "async def run(state):\n"
                    "    user_text = state.get('content', '')\n"
                    "    state['response'] = f'embed-ok:{user_text}'\n"
                    "    return state"
                ),
            }
        },
        edges=[Edge(from_node="main", to_node=None)],
    )
    await FlowConfig.create_version(agent)
    await di.flow_access_service.sync_flow_saved(
        agent,
        company_id=company_id,
        owner_user_id=user_id,
    )
    clear_context()

    token = get_token_service().create_token(user_id, company_id=company_id)
    yield {"Authorization": f"Bearer {token}"}, flow_id, company_id, user_id

    set_context(
        Context(
            user=User(user_id=user_id, name="Test"),
            active_company=Company(company_id=company_id, name="Test Company"),
            session_id="test",
            channel="test",
        )
    )
    await di.flow_access_service.sync_flow_deleted(
        flow_id, company_id=company_id, branch_ids=[]
    )
    await FlowConfig.delete_by_flow_id(flow_id)
    clear_context()
