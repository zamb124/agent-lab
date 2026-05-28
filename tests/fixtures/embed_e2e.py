"""Подготовка изолированной компании, пользователя и code-агента для E2E embed (поток A2A)."""

from __future__ import annotations

import pytest_asyncio

from core.context import Context, clear_context, set_context
from core.models.identity_models import Company, User
from core.utils.tokens import get_token_service


@pytest_asyncio.fixture
async def embed_test_auth(frontend_container, unique_id):
    from apps.flows.src.container import get_container
    from apps.flows.src.models.flow_config import Edge, FlowConfig

    company_id = f"test_company_{unique_id}"
    company = Company(
        company_id=company_id,
        name="Test Company",
        owner_user_id="test_user",
    )
    await frontend_container.company_repository.set(company)

    user_id = f"test_user_{unique_id}"
    user = User(
        user_id=user_id,
        name="Test User",
        emails=[f"{user_id}@test.com"],
        companies={company_id: ["admin"]},
        active_company_id=company_id,
    )
    await frontend_container.user_repository.set(user)
    company.members = {user_id: ["admin"]}
    await frontend_container.company_repository.set(company)

    set_context(
        Context(
            user=User(user_id=user_id, name="Test"),
            active_company=Company(company_id=company_id, name="Test Company"),
            session_id="test",
            channel="test",
        )
    )
    flows_container = get_container()
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
    await flows_container.flow_repository.set(agent)
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
    await flows_container.flow_repository.delete(flow_id)
    clear_context()
