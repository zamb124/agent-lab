"""Доверенный runtime-эндпоинт для исполнения platform tools через capability-gateway."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from fastapi import APIRouter, HTTPException
from pydantic import Field, ValidationError

from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.runners.tool_context_view import build_tool_context_view
from apps.flows.src.runtime.exceptions import FlowInterrupt
from apps.flows.src.runtime.tool_call_context import active_tool_call_context
from core.capabilities import (
    CAPABILITY_LANGUAGES,
    CapabilityCallResponse,
    CapabilityDefinition,
    CapabilityExecutionContext,
    CapabilityInterruptEnvelope,
    CapabilityManifest,
    verify_execution_context,
)
from core.context import clear_context, get_context, set_context
from core.context.job_context import build_job_context
from core.logging import get_logger
from core.models import StrictBaseModel
from core.models.context_models import Context
from core.state import ExecutionState
from core.types import JsonObject, require_json_object

logger = get_logger(__name__)

router = APIRouter(tags=["tool-runtime"])
_RESERVED_SDK_METHODS = frozenset({"call", "then"})


class ToolRuntimeCallRequest(StrictBaseModel):
    context: CapabilityExecutionContext
    tool_id: str = Field(..., min_length=1)
    arguments: JsonObject = Field(default_factory=dict)
    state: JsonObject = Field(default_factory=dict)


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
    input_schema: JsonObject,
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


async def collect_tool_runtime_capabilities(
    container: ContainerDep,
) -> dict[str, CapabilityDefinition]:
    """Builtin docs tools + tool_repository текущей компании, если context есть."""
    registry = container.tool_registry
    registry.register_builtin_tools()
    capabilities: dict[str, CapabilityDefinition] = {}
    for tool_id, tool in registry.list_all().items():
        if not tool.listed_in_platform_tool_docs:
            continue
        capabilities[f"tools.{tool_id}"] = _tool_capability_definition(
            tool_id=tool_id,
            title=None,
            description=tool.description,
            input_schema=tool.parameters,
            tags=tool.get_tags(),
        )
    context = get_context()
    if context is not None and context.active_company is not None:
        for tool in await container.tool_repository.list(limit=10000):
            capabilities[f"tools.{tool.tool_id}"] = _tool_capability_definition(
                tool_id=tool.tool_id,
                title=tool.title or tool.name,
                description=tool.description,
                input_schema=tool.effective_parameters_schema(),
                tags=tool.tags or ["misc"],
            )
    return capabilities


@router.get("/manifest", response_model=CapabilityManifest)
async def get_tool_runtime_manifest(
    container: ContainerDep,
    allowed_capabilities: str | None = None,
) -> CapabilityManifest:
    """Возвращает каждый platform tool как first-class capability ``tools.<tool_id>``."""
    capabilities = await collect_tool_runtime_capabilities(container)
    capability_list = [capabilities[name] for name in sorted(capabilities)]
    if allowed_capabilities:
        allowed_names = {
            item.strip()
            for item in allowed_capabilities.split(",")
            if item.strip()
        }
        capability_list = [
            capability
            for capability in capability_list
            if capability.name in allowed_names
        ]
    return CapabilityManifest(
        version="capabilities.v1",
        capabilities=capability_list,
    )


@router.post("/call", response_model=CapabilityCallResponse)
async def call_tool_runtime(
    container: ContainerDep,
    request: ToolRuntimeCallRequest,
) -> CapabilityCallResponse:
    """Исполняет любой зарегистрированный platform tool по id с подписанным capability context."""
    verify_execution_context(request.context)
    runtime_context = await _build_context(container, request.context)
    previous_context = get_context()
    _ = set_context(runtime_context)
    try:
        state = ExecutionState.model_validate(request.state)
        _attach_durable_context(state, request.context)
        tool = await container.tool_registry.materialize({"tool_id": request.tool_id})
        try:
            with _active_tool_runtime_context(request, state):
                result = await tool.run(request.arguments, state)
        except FlowInterrupt as exc:
            body = require_json_object(exc.body.model_dump(mode="json"), "FlowInterrupt.body")
            raw_kind = body.get("kind")
            if not isinstance(raw_kind, str):
                raise ValueError("FlowInterrupt.body.kind must be a string")
            return CapabilityCallResponse(
                status="interrupt",
                state=build_tool_context_view(state),
                interrupt=CapabilityInterruptEnvelope(
                    kind=raw_kind,
                    body=body,
                    correlation_id=str(exc.correlation_id) if exc.correlation_id is not None else None,
                ),
            )
        except ValidationError as exc:
            logger.info(
                "tool_runtime.arguments_invalid tool_id=%s error_count=%s",
                request.tool_id,
                exc.error_count(),
            )
            raise HTTPException(
                status_code=422,
                detail={
                    "tool_id": request.tool_id,
                    "message": "Tool arguments failed validation",
                    "errors": exc.errors(),
                },
            ) from exc
        return CapabilityCallResponse(
            status="ok",
            result=result,
            state=build_tool_context_view(state),
        )
    finally:
        if previous_context is None:
            clear_context()
        else:
            _ = set_context(previous_context)


def _attach_durable_context(
    state: ExecutionState,
    execution_context: CapabilityExecutionContext,
) -> None:
    state.attach_durable_node_context(
        execution_branch_id=execution_context.durable_execution_branch_id,
        node_schedule_sequence=execution_context.durable_node_schedule_sequence,
        superstep_sequence=execution_context.durable_superstep_sequence,
    )


@contextmanager
def _active_tool_runtime_context(
    request: ToolRuntimeCallRequest,
    state: ExecutionState,
) -> Generator[None, None, None]:
    source_node_id = request.context.source_node_id
    source_tool_call_id = request.context.source_tool_call_id
    if source_node_id is None and source_tool_call_id is None:
        yield
        return
    if source_node_id is None or source_tool_call_id is None:
        raise ValueError(
            "Capability tool runtime context requires both source_node_id and source_tool_call_id"
        )
    with active_tool_call_context(
        tool_name=request.tool_id,
        tool_call_id=source_tool_call_id,
        node_id=source_node_id,
        state=state,
    ):
        yield


async def _build_context(container: ContainerDep, execution_context: CapabilityExecutionContext) -> Context:
    if execution_context.user_id is None:
        raise HTTPException(status_code=401, detail="Capability context requires user_id")
    user = await container.user_repository.get(execution_context.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail=f"User not found: {execution_context.user_id}")
    company = await container.company_repository.get(execution_context.company_id)
    if company is None:
        raise HTTPException(status_code=401, detail=f"Company not found: {execution_context.company_id}")
    trace_id = execution_context.trace_id
    if trace_id is None:
        request_id = execution_context.request_id
        if isinstance(request_id, str) and request_id.strip():
            trace_id = request_id.strip()
        else:
            trace_id = f"tool-runtime:{execution_context.session_id}"
    company_subdomain = company.subdomain
    if company_subdomain is None or company_subdomain.strip() == "":
        host = company.company_id
    else:
        host = company_subdomain.strip()
    job_context = build_job_context(
        company=company,
        user=user,
        host=host,
        trace_id=trace_id,
        session_id=execution_context.session_id,
        channel=execution_context.channel,
    )
    updates: dict[str, object] = {"flow_id": execution_context.flow_id}
    if execution_context.namespace is not None:
        updates["active_namespace"] = execution_context.namespace
    return job_context.model_copy(update=updates)
