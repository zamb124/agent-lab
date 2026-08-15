"""Shared fixtures for tests under tests/flows/."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextvars import Token

import pytest

from apps.flows.src.models import BranchConfig, Edge, FlowConfig
from core.context import get_context, reset_context, set_context
from core.models.context_models import Context
from core.models.identity_models import User
from tests.fixtures.ai_provider_defaults import make_test_company


def _bind_flow_company_context(company_id: str) -> Token[Context | None]:
    previous = get_context()
    user = (
        previous.user
        if previous is not None
        else User(user_id="test_user", name="Test User")
    )
    metadata = dict(previous.metadata) if previous is not None else {}
    return set_context(
        Context(
            user=user,
            active_company=make_test_company(company_id=company_id, name="Perm"),
            session_id="test_session",
            channel="test",
            metadata=metadata,
        )
    )


@pytest.fixture
async def flow_with_permission(container, unique_id) -> AsyncIterator[str]:
    """Flow с permission=managers + OpenFGA tuples в той же company, что Check."""
    flow_id = f"perm_flow_{unique_id}"
    company_id = f"perm_co_{unique_id}"
    token = _bind_flow_company_context(company_id)

    config = FlowConfig(
        flow_id=flow_id,
        name="Permission Test Agent",
        entry="main",
        permission="managers",
        nodes={
            "main": {
                "type": "code",
                "code": "async def run(args, state): state['response'] = 'Agent executed'; return state",
            }
        },
        edges=[Edge(from_node="main", to_node=None)],
    )

    try:
        await container.flow_repository.set(config)
        await container.flow_access_service.sync_flow_saved(
            config,
            company_id=company_id,
            owner_user_id=f"owner_{unique_id}",
        )
        yield flow_id
        await container.flow_access_service.sync_flow_deleted(
            flow_id, company_id=company_id, branch_ids=[]
        )
        await container.flow_repository.delete(flow_id)
    finally:
        reset_context(token)


@pytest.fixture
async def flow_with_skill_permission(container, unique_id) -> AsyncIterator[str]:
    """Flow с branch vip (permission=vip) + OpenFGA tuples в той же company, что Check."""
    flow_id = f"skill_perm_flow_{unique_id}"
    company_id = f"skill_co_{unique_id}"
    token = _bind_flow_company_context(company_id)

    config = FlowConfig(
        flow_id=flow_id,
        name="Skill Permission Test Agent",
        entry="main",
        permission=["users", "vip"],
        nodes={
            "main": {
                "type": "code",
                "code": "async def run(args, state): state['response'] = 'Default skill'; return state",
            },
            "vip_main": {
                "type": "code",
                "code": "async def run(args, state): state['response'] = 'VIP skill'; return state",
            },
        },
        edges=[
            Edge(from_node="main", to_node=None),
            Edge(from_node="vip_main", to_node=None),
        ],
        branches={
            "default": BranchConfig(name="Default"),
            "vip": BranchConfig(
                name="VIP Skill",
                entry="vip_main",
                permission="vip",
            ),
        },
    )

    try:
        await container.flow_repository.set(config)
        await container.flow_access_service.sync_flow_saved(
            config,
            company_id=company_id,
            owner_user_id=f"owner_{unique_id}",
        )
        yield flow_id
        await container.flow_access_service.sync_flow_deleted(
            flow_id, company_id=company_id, branch_ids=list(config.branches.keys())
        )
        await container.flow_repository.delete(flow_id)
    finally:
        reset_context(token)
