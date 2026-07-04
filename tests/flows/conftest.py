"""Shared fixtures for tests under tests/flows/."""

from __future__ import annotations

import pytest

from apps.flows.src.models import BranchConfig, Edge, FlowConfig


@pytest.fixture
def flows_permissions_enabled():
    """
    Включает permissions на время теста через явный try/finally на settings.
    Не monkeypatch: один documented harness для channel-level тестов.
    """
    from apps.flows.config import get_settings

    config = get_settings()
    original = config.auth.permissions_enabled
    config.auth.permissions_enabled = True
    try:
        yield
    finally:
        config.auth.permissions_enabled = original


@pytest.fixture
async def flow_with_permission(container, unique_id):
    """Flow с permission=managers."""
    flow_id = f"perm_flow_{unique_id}"

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

    yield flow_id

    await container.flow_repository.delete(flow_id)


@pytest.fixture
async def flow_with_skill_permission(container, unique_id):
    """Flow с branch vip (permission=vip)."""
    flow_id = f"skill_perm_flow_{unique_id}"

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

    yield flow_id

    await container.flow_repository.delete(flow_id)
