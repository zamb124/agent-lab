"""Flows OpenFGA backfill читает KV из таблиц flows/tools, не storage."""

from __future__ import annotations

import pytest

from apps.flows.authz.backfill import parse_company_resource_key, tool_permission_from_payload
from apps.flows.authz.tuples import flow_company_viewer_tuple
from apps.flows.src.models import Edge, FlowConfig
from core.config import get_settings
from core.context import reset_context, set_context
from core.db.storage import Storage
from core.models.context_models import Context
from core.models.identity_models import User
from tests.fixtures.ai_provider_defaults import make_test_company


def test_parse_company_resource_key_flow() -> None:
    assert parse_company_resource_key("company:system:flow:lara", "flow") == (
        "system",
        "lara",
    )


def test_parse_company_resource_key_mcp_tool() -> None:
    assert parse_company_resource_key(
        "company:system:tool:mcp:io_github_x:book_plumber",
        "tool",
    ) == ("system", "mcp:io_github_x:book_plumber")


def test_parse_company_resource_key_rejects_other_resource() -> None:
    assert parse_company_resource_key("company:system:flow:lara", "tool") is None


def test_flow_company_viewer_tuple_uses_scoped_object_key() -> None:
    item = flow_company_viewer_tuple("lara", "system")
    assert item.obj.object_key == "system/lara"


def test_tool_permission_from_payload_ignores_legacy_extra_fields() -> None:
    permission = tool_permission_from_payload(
        {
            "tool_id": "mcp:io_github_x:book",
            "permission": [],
            "mock_map": None,
            "parameters_schema": {},
        },
        storage_key="company:system:tool:mcp:io_github_x:book",
        tool_id="mcp:io_github_x:book",
    )
    assert permission == []


@pytest.mark.asyncio
async def test_flow_kv_is_in_flows_table_not_storage_prefix_scan(
    container,
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
        _ = await container.flow_repository.set(config)
        storage = Storage(db_url=str(get_settings().database.flows_url))
        storage_prefix_rows = await storage.get_all_by_prefix("company:", limit=1000)
        flow_table_rows = await storage.get_all_by_prefix_and_table(
            f"company:{company_id}:flow:",
            "flows",
            limit=100,
        )
    finally:
        reset_context(context_token)

    assert storage_key not in storage_prefix_rows
    assert storage_key in flow_table_rows
