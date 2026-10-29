"""Prod-like: tools REST и `op_*` — один handler."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

import pytest
from httpx2 import AsyncClient

from apps.flows.di import FlowsDi
from apps.flows.realtime.tool_operations import (
    op_flows_tools_contract,
    op_flows_tools_create,
    op_flows_tools_item,
    op_flows_tools_list,
    op_flows_tools_list_all,
    op_flows_tools_preview,
    op_flows_tools_remove,
    op_flows_tools_tag_groups,
)
from apps.flows.src.models.tool_contracts import ToolDefinition
from apps.flows.src.models.tool_reference import (
    PickerCategory,
    ToolCreateRequest,
    ToolResponse,
    ToolsListAllPayload,
    ToolsListPayload,
    ToolsTagGroupsPayload,
    ToolsToolIdPayload,
)
from apps.flows.src.models.tool_tag_group import ToolTagGroup
from apps.flows.src.services.tool_preview import ToolPreviewRequest, ToolPreviewResponse
from core.context import reset_context, set_context
from core.models.context_models import Context
from core.models.identity_models import User
from core.pagination import OffsetPage
from core.types import JsonObject
from tests.fixtures.ai_provider_defaults import make_test_company

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(60)]


@contextmanager
def _system_scope(system_user_id: str) -> Generator[User]:
    user = User(user_id=system_user_id, name="System")
    token = set_context(
        Context(
            user=user,
            active_company=make_test_company(company_id="system", name="System"),
            channel="api",
        )
    )
    try:
        yield user
    finally:
        reset_context(token)


def _inline_schema() -> JsonObject:
    return {"type": "object", "properties": {}, "required": []}


async def test_tools_list_rest_and_op_share_payload(
    client: AsyncClient,
    di: FlowsDi,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    payload = ToolsListPayload(limit=20, offset=0)
    http_resp = await client.get(
        "/flows/api/v1/tools/?limit=20&offset=0",
        headers=auth_headers_system,
    )
    assert http_resp.status_code == 200, http_resp.text
    _ = OffsetPage[ToolResponse].model_validate(http_resp.json())
    with _system_scope(system_user_id) as user:
        listed = await op_flows_tools_list(payload, user=user, di=di)
    assert listed.model_dump(mode="json") == http_resp.json()


async def test_tools_create_get_remove_rest_and_op_share_payload(
    client: AsyncClient,
    di: FlowsDi,
    unique_id: str,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    tool_id = f"cmd_tool_{unique_id}"
    create_payload = ToolCreateRequest(
        tool_id=tool_id,
        title="Command tool",
        description="inline",
        code="async def run(args, state):\n    return args",
        parameters_schema=_inline_schema(),
    )
    http_create = await client.post(
        "/flows/api/v1/tools/",
        headers=auth_headers_system,
        json=create_payload.model_dump(mode="json"),
    )
    assert http_create.status_code == 200, http_create.text
    created = ToolResponse.model_validate(http_create.json())
    assert created.tool_id == tool_id

    item_payload = ToolsToolIdPayload(tool_id=tool_id)
    http_get = await client.get(
        f"/flows/api/v1/tools/{tool_id}",
        headers=auth_headers_system,
    )
    assert http_get.status_code == 200, http_get.text
    with _system_scope(system_user_id) as user:
        op_item = await op_flows_tools_item(item_payload, user=user, di=di)
    assert op_item.model_dump(mode="json") == http_get.json()

    http_delete = await client.delete(
        f"/flows/api/v1/tools/{tool_id}",
        headers=auth_headers_system,
    )
    assert http_delete.status_code == 200, http_delete.text
    assert http_delete.json() == {"status": "deleted", "tool_id": tool_id}

    op_tool_id = f"cmd_tool_op_{unique_id}"
    op_create = ToolCreateRequest(
        tool_id=op_tool_id,
        title="Command tool op",
        description="inline",
        code="async def run(args, state):\n    return args",
        parameters_schema=_inline_schema(),
    )
    with _system_scope(system_user_id) as user:
        created_op = await op_flows_tools_create(op_create, user=user, di=di)
        removed = await op_flows_tools_remove(
            ToolsToolIdPayload(tool_id=op_tool_id),
            user=user,
            di=di,
        )
    assert created_op.tool_id == op_tool_id
    assert removed.model_dump(mode="json") == {"status": "deleted", "tool_id": op_tool_id}


async def test_tools_list_all_rest_and_op_share_payload(
    client: AsyncClient,
    di: FlowsDi,
    unique_id: str,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    tool_id = f"cmd_picker_{unique_id}"
    create = await client.post(
        "/flows/api/v1/tools/",
        headers=auth_headers_system,
        json=ToolCreateRequest(
            tool_id=tool_id,
            title=tool_id,
            description="picker",
            code="async def run(args, state):\n    return args",
            parameters_schema=_inline_schema(),
        ).model_dump(mode="json"),
    )
    assert create.status_code == 200, create.text
    payload = ToolsListAllPayload(
        limit=20,
        offset=0,
        picker_category=PickerCategory.CODE,
        q=tool_id,
    )
    http_resp = await client.get(
        f"/flows/api/v1/tools/all?limit=20&offset=0&picker_category=code&q={tool_id}",
        headers=auth_headers_system,
    )
    assert http_resp.status_code == 200, http_resp.text
    with _system_scope(system_user_id) as user:
        listed = await op_flows_tools_list_all(payload, user=user, di=di)
    assert listed.model_dump(mode="json") == http_resp.json()
    assert any(item.tool_id == tool_id for item in listed.items)


async def test_tools_tag_groups_rest_and_op_share_payload(
    client: AsyncClient,
    di: FlowsDi,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    payload = ToolsTagGroupsPayload(limit=200, offset=0)
    http_resp = await client.get(
        "/flows/api/v1/tools/tag-groups?limit=200&offset=0",
        headers=auth_headers_system,
    )
    assert http_resp.status_code == 200, http_resp.text
    _ = OffsetPage[ToolTagGroup].model_validate(http_resp.json())
    with _system_scope(system_user_id) as user:
        listed = await op_flows_tools_tag_groups(payload, user=user, di=di)
    assert listed.model_dump(mode="json") == http_resp.json()


async def test_tools_preview_rest_and_op_share_payload(
    client: AsyncClient,
    di: FlowsDi,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    payload = ToolPreviewRequest(
        tool_id="wiki_get_page",
        model_args={"wiki_page_id": "p1", "api_token": "super-secret"},
    )
    http_resp = await client.post(
        "/flows/api/v1/tools/preview",
        headers=auth_headers_system,
        json=payload.model_dump(mode="json"),
    )
    assert http_resp.status_code == 200, http_resp.text
    _ = ToolPreviewResponse.model_validate(http_resp.json())
    with _system_scope(system_user_id) as user:
        previewed = await op_flows_tools_preview(payload, user=user, di=di)
    assert previewed.model_dump(mode="json") == http_resp.json()


async def test_tools_contract_rest_and_op_share_payload(
    client: AsyncClient,
    di: FlowsDi,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    payload = ToolsToolIdPayload(tool_id="wiki_create_page")
    http_resp = await client.get(
        "/flows/api/v1/tools/wiki_create_page/contract",
        headers=auth_headers_system,
    )
    assert http_resp.status_code == 200, http_resp.text
    _ = ToolDefinition.model_validate(http_resp.json())
    with _system_scope(system_user_id) as user:
        contract = await op_flows_tools_contract(payload, user=user, di=di)
    assert contract.model_dump(mode="json") == http_resp.json()
