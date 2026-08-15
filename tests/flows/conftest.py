"""Shared fixtures for tests under tests/flows/."""

from __future__ import annotations

import pytest

from apps.flows.src.models import BranchConfig, Edge, FlowConfig


@pytest.fixture
async def flow_with_permission(container, unique_id):
    """Flow с permission=managers + OpenFGA tuples."""
    flow_id = f"perm_flow_{unique_id}"
    company_id = f"perm_co_{unique_id}"

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

    await container.flow_repository.set(config)
    await container.flow_access_service.sync_flow_saved(
        config,
        company_id=company_id,
        owner_user_id=f"owner_{unique_id}",
    )

    yield flow_id

    await container.flow_access_service.sync_flow_deleted(flow_id, branch_ids=[])
    await container.flow_repository.delete(flow_id)


@pytest.fixture
async def flow_with_skill_permission(container, unique_id):
    """Flow с branch vip (permission=vip) + OpenFGA tuples."""
    flow_id = f"skill_perm_flow_{unique_id}"
    company_id = f"skill_co_{unique_id}"

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

    await container.flow_repository.set(config)
    await container.flow_access_service.sync_flow_saved(
        config,
        company_id=company_id,
        owner_user_id=f"owner_{unique_id}",
    )

    yield flow_id

    await container.flow_access_service.sync_flow_deleted(
        flow_id, branch_ids=list(config.branches.keys())
    )
    await container.flow_repository.delete(flow_id)
