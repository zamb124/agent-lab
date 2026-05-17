"""Trusted runtime endpoint for executing platform tools through capability-gateway."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.runtime.exceptions import FlowInterrupt
from core.capabilities import (
    CAPABILITY_LANGUAGES,
    CapabilityDefinition,
    CapabilityExecutionContext,
    CapabilityInterruptEnvelope,
    CapabilityManifest,
    verify_execution_context,
)
from core.context import clear_context, get_context, set_context
from core.models.context_models import Context
from core.models.i18n_models import Language
from core.models.identity_models import Company, User
from core.state import ExecutionState

router = APIRouter(tags=["tool-runtime"])
_RESERVED_SDK_METHODS = frozenset({"call", "then"})


class ToolRuntimeCallRequest(BaseModel):
    context: CapabilityExecutionContext
    tool_id: str = Field(..., min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    state: dict[str, Any] = Field(default_factory=dict)


class ToolRuntimeCallResponse(BaseModel):
    status: Literal["ok", "interrupt"]
    result: Any = None
    state: dict[str, Any] = Field(default_factory=dict)
    interrupt: CapabilityInterruptEnvelope | None = None


def _sdk_method_name(raw: str) -> str:
    name = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in raw).strip("_")
    if not name:
        name = "tool"
    if name[0].isdigit():
        name = f"tool_{name}"
    if name in _RESERVED_SDK_METHODS:
        name = f"tool_{name}"
    return name


def _tool_capability_definition(
    *,
    tool_id: str,
    title: str | None,
    description: str | None,
    input_schema: dict[str, Any],
    tags: list[str],
) -> CapabilityDefinition:
    return CapabilityDefinition(
        name=f"tools.{tool_id}",
        title=title or tool_id,
        description=description or f"Platform tool {tool_id}",
        input_schema=input_schema,
        output_schema={"description": "JSON-результат platform tool; форма зависит от tool_id."},
        languages=list(CAPABILITY_LANGUAGES),
        tags=["tools", *tags],
        sdk_namespace="tools",
        sdk_method=_sdk_method_name(tool_id),
    )


async def _with_system_context_if_missing(container: Any):
    previous_context = get_context()
    if previous_context is not None and previous_context.active_company is not None:
        return previous_context, False
    set_context(
        Context(
            user=User(user_id="system", name="System", groups=["admin"]),
            host="system",
            session_id="tool-runtime-manifest",
            channel="internal",
            language=Language.RU,
            active_company=Company(
                company_id="system",
                name="System",
                subdomain="system",
            ),
            user_companies=[],
            trace_id="tool-runtime:manifest",
        )
    )
    _ = container
    return previous_context, True


@router.get("/manifest", response_model=CapabilityManifest)
async def get_tool_runtime_manifest(container: ContainerDep) -> CapabilityManifest:
    """Return every platform tool as a first-class `tools.<tool_id>` capability."""
    previous_context, installed_context = await _with_system_context_if_missing(container)
    try:
        registry = container.tool_registry
        registry.register_builtin_tools()
        capabilities: dict[str, CapabilityDefinition] = {}

        for tool_id, tool in registry.list_all().items():
            if not getattr(tool, "listed_in_platform_tool_docs", True):
                continue
            capabilities[f"tools.{tool_id}"] = _tool_capability_definition(
                tool_id=tool_id,
                title=getattr(tool, "title", None),
                description=getattr(tool, "description", None),
                input_schema=tool.parameters,
                tags=tool.get_tags(),
            )

        for tool in await container.tool_repository.list(limit=10000):
            capabilities[f"tools.{tool.tool_id}"] = _tool_capability_definition(
                tool_id=tool.tool_id,
                title=tool.title or tool.name,
                description=tool.description,
                input_schema=tool.effective_parameters_schema(),
                tags=tool.tags or ["misc"],
            )

        return CapabilityManifest(
            version="capabilities.v1",
            capabilities=[capabilities[name] for name in sorted(capabilities)],
        )
    finally:
        if installed_context:
            if previous_context is None:
                clear_context()
            else:
                set_context(previous_context)
        elif previous_context is not None:
            set_context(previous_context)


@router.post("/call", response_model=ToolRuntimeCallResponse)
async def call_tool_runtime(
    container: ContainerDep,
    request: ToolRuntimeCallRequest,
) -> ToolRuntimeCallResponse:
    """Execute any registered platform tool by id using signed capability context."""
    verify_execution_context(request.context)
    runtime_context = await _build_context(container, request.context)
    previous_context = get_context()
    set_context(runtime_context)
    try:
        state = ExecutionState.model_validate(request.state)
        tool = await container.tool_registry.materialize({"tool_id": request.tool_id})
        try:
            result = await tool.run(dict(request.arguments), state)
        except FlowInterrupt as exc:
            body = exc.body.model_dump(mode="json")
            return ToolRuntimeCallResponse(
                status="interrupt",
                state=state.model_dump(mode="json", exclude_none=False),
                interrupt=CapabilityInterruptEnvelope(
                    kind=str(body.get("kind", "interrupt")),
                    body=body,
                ),
            )
        return ToolRuntimeCallResponse(
            status="ok",
            result=result,
            state=state.model_dump(mode="json", exclude_none=False),
        )
    finally:
        if previous_context is None:
            clear_context()
        else:
            set_context(previous_context)


async def _build_context(container: Any, execution_context: CapabilityExecutionContext) -> Context:
    if execution_context.user_id is None:
        raise HTTPException(status_code=401, detail="Capability context requires user_id")
    user = await container.user_repository.get(execution_context.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail=f"User not found: {execution_context.user_id}")
    company = await container.company_repository.get(execution_context.company_id)
    if company is None:
        raise HTTPException(status_code=401, detail=f"Company not found: {execution_context.company_id}")
    return Context(
        user=user,
        active_company=company,
        user_companies=[company],
        session_id=execution_context.session_id,
        channel="tool_runtime",
        flow_id=execution_context.flow_id,
        trace_id=execution_context.trace_id,
    )
