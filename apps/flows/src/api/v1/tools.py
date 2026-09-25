"""REST-зеркало каталога tools: path/query → тот же `op_*`, что и WS."""

from typing import Annotated

from fastapi import APIRouter, Query

from apps.flows.di import Di
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
    ToolDeletedResponse,
    ToolResponse,
    ToolsListAllPayload,
    ToolsListPayload,
    ToolsTagGroupsPayload,
    ToolsToolIdPayload,
)
from apps.flows.src.models.tool_tag_group import ToolTagGroup
from apps.flows.src.services.tool_preview import ToolPreviewRequest, ToolPreviewResponse
from core.context import require_context
from core.pagination import OffsetPage

router = APIRouter(tags=["tools"])


@router.get("/", response_model=OffsetPage[ToolResponse])
async def list_tools(
    di: Di,
    limit: Annotated[int, Query(ge=1, le=2000, description="Максимум tools")] = 500,
    offset: Annotated[int, Query(ge=0, description="Смещение для пагинации")] = 0,
) -> OffsetPage[ToolResponse]:
    return await op_flows_tools_list(
        ToolsListPayload(limit=limit, offset=offset),
        user=require_context().user,
        di=di,
    )


@router.get("/all", response_model=OffsetPage[ToolResponse])
async def list_all_tools_and_flows(
    di: Di,
    limit: Annotated[
        int,
        Query(ge=1, le=20, description="Максимум tools+flows на страницу"),
    ] = 20,
    offset: Annotated[int, Query(ge=0, description="Смещение для пагинации")] = 0,
    picker_category: Annotated[
        PickerCategory | None,
        Query(description="Категория для tool picker: all, code, flow, mcp"),
    ] = None,
    q: Annotated[str | None, Query(description="Поиск по tool_id / title / description")] = None,
) -> OffsetPage[ToolResponse]:
    return await op_flows_tools_list_all(
        ToolsListAllPayload(
            limit=limit,
            offset=offset,
            picker_category=picker_category,
            q=q,
        ),
        user=require_context().user,
        di=di,
    )


@router.get("/tag-groups", response_model=OffsetPage[ToolTagGroup])
async def list_tool_tag_groups(
    di: Di,
    limit: Annotated[int, Query(ge=1, le=200)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[ToolTagGroup]:
    return await op_flows_tools_tag_groups(
        ToolsTagGroupsPayload(limit=limit, offset=offset),
        user=require_context().user,
        di=di,
    )


@router.post("/preview", response_model=ToolPreviewResponse)
async def preview_tool(
    request: ToolPreviewRequest, di: Di
) -> ToolPreviewResponse:
    return await op_flows_tools_preview(
        request, user=require_context().user, di=di
    )


@router.get("/{tool_id}/contract", response_model=ToolDefinition)
async def get_tool_contract(tool_id: str, di: Di) -> ToolDefinition:
    return await op_flows_tools_contract(
        ToolsToolIdPayload(tool_id=tool_id),
        user=require_context().user,
        di=di,
    )


@router.get("/{tool_id}", response_model=ToolResponse)
async def get_tool(tool_id: str, di: Di) -> ToolResponse:
    return await op_flows_tools_item(
        ToolsToolIdPayload(tool_id=tool_id),
        user=require_context().user,
        di=di,
    )


@router.post("/", response_model=ToolResponse)
async def create_tool(request: ToolCreateRequest, di: Di) -> ToolResponse:
    return await op_flows_tools_create(
        request, user=require_context().user, di=di
    )


@router.delete("/{tool_id}", response_model=ToolDeletedResponse)
async def delete_tool(tool_id: str, di: Di) -> ToolDeletedResponse:
    return await op_flows_tools_remove(
        ToolsToolIdPayload(tool_id=tool_id),
        user=require_context().user,
        di=di,
    )
