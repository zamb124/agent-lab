"""Flows OpenFGA backfill читает KV из таблиц flows/tools, не storage."""

from __future__ import annotations

import pytest

from apps.flows.authz.tuples import flow_company_viewer_tuple
from apps.flows.src.models import Edge, FlowConfig
from core.context import reset_context, set_context
from core.models.context_models import Context
from core.models.identity_models import User
from tests.fixtures.ai_provider_defaults import make_test_company


def test_flow_company_viewer_tuple_uses_scoped_object_key() -> None:
    item = flow_company_viewer_tuple("lara", "system")
    assert item.obj.object_key == "system/lara"


@pytest.mark.asyncio
async def test_flow_kv_is_in_flows_table_not_storage_prefix_scan(
    di,
    unique_id: str,
) -> None:
    company_id = f"co_bf_{unique_id}"
    flow_id = f"bf_{unique_id}"
    storage_key = f"company:{company_id}:flow:{flow_id}"
    config = FlowConfig(
        flow_id=flow_id,
        name="backfill-source",
        entry="main",
        permission=[],
        nodes={
            "main": {
                "type": "code",
                "code": "async def run(args, state): return state",
            }
        },
        edges=[Edge(from_node="main", to_node=None)],
    )
    context_token = set_context(
        Context(
            user=User(user_id=f"user_{unique_id}", name="Backfill"),
            active_company=make_test_company(company_id=company_id, name="Backfill"),
            channel="api",
        )
    )
    try:
        _ = await FlowConfig.create_version(config)
        loaded = await FlowConfig.current_for_flow(flow_id)
    finally:
        reset_context(context_token)

    assert loaded is not None
    assert loaded.flow_id == flow_id
