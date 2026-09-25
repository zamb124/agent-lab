"""REST-зеркало tool runtime для capability-gateway (`flows/tool_runtime/*`)."""

from __future__ import annotations

from fastapi import APIRouter

from apps.flows.di import Di
from apps.flows.realtime.tool_runtime_operations import (
    ToolRuntimeCallPayload,
    ToolRuntimeManifestPayload,
    op_flows_tool_runtime_call,
    op_flows_tool_runtime_manifest,
)
from core.capabilities import CapabilityCallResponse, CapabilityManifest
from core.context import require_context

router = APIRouter(tags=["tool-runtime"])


@router.get("/manifest", response_model=CapabilityManifest)
async def get_tool_runtime_manifest(
    di: Di,
    allowed_capabilities: str | None = None,
) -> CapabilityManifest:
    """Каждый platform tool как first-class capability ``tools.<tool_id>``."""
    allowed = (
        [item for item in allowed_capabilities.split(",") if item.strip()]
        if allowed_capabilities
        else None
    )
    return await op_flows_tool_runtime_manifest(
        ToolRuntimeManifestPayload(allowed_capabilities=allowed),
        user=require_context().user,
        di=di,
    )


@router.post("/call", response_model=CapabilityCallResponse)
async def call_tool_runtime(
    di: Di,
    request_body: ToolRuntimeCallPayload,
) -> CapabilityCallResponse:
    return await op_flows_tool_runtime_call(
        request_body,
        user=require_context().user,
        di=di,
    )
