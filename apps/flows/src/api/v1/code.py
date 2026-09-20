"""REST-зеркало code editor: тот же `op_*`, что и WS. LSP — `code_lsp.py`."""

from fastapi import APIRouter
from pydantic import ValidationError

from apps.flows.realtime.code_operations import (
    op_flows_code_documentation,
    op_flows_code_editor_state,
    op_flows_code_execute,
    op_flows_code_flow_functions,
    op_flows_code_parse_signature,
    op_flows_code_source,
    op_flows_code_templates,
    op_flows_code_tool_source,
    op_flows_code_validate,
)
from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.models.code_api import (
    CodeDocumentationPayload,
    CodeDocumentationResponse,
    CodeEditorStatePayload,
    CodeFlowFunctionsPayload,
    CodeSourcePayload,
    CodeTemplatesPayload,
    CodeToolSourcePayload,
    ExecuteRequest,
    ExecuteResponse,
    FlowFunctionsResponse,
    ParseSignatureRequest,
    ParseSignatureResponse,
    SourceResponse,
    TemplatesResponse,
    ValidateRequest,
    ValidateResponse,
)
from core.context import require_context
from core.types import JsonObject
from core.websocket import (
    raise_invalid,
)

router = APIRouter(tags=["code"])


@router.get("/documentation", response_model=CodeDocumentationResponse)
async def get_code_documentation(
    container: ContainerDep,
    language: str = "python",
    perspective: str = "editor",
    include_runtime_namespace_extras: bool = False,
) -> CodeDocumentationResponse:
    return await op_flows_code_documentation(
        CodeDocumentationPayload(
            language=language,
            perspective=perspective,
            include_runtime_namespace_extras=include_runtime_namespace_extras,
        ),
        user=require_context().user,
        container=container,
    )


@router.get("/templates", response_model=TemplatesResponse)
async def get_code_templates(
    container: ContainerDep,
    language: str = "python",
    category: str | None = None,
    node_type: str | None = None,
    tags: str | None = None,
) -> TemplatesResponse:
    return await op_flows_code_templates(
        CodeTemplatesPayload(
            language=language,
            category=category,
            node_type=node_type,
            tags=tags,
        ),
        user=require_context().user,
        container=container,
    )


@router.get("/editor-state")
async def get_editor_state(
    container: ContainerDep,
    flow_id: str,
    branch_id: str = "default",
) -> JsonObject:
    return await op_flows_code_editor_state(
        CodeEditorStatePayload(flow_id=flow_id, branch_id=branch_id),
        user=require_context().user,
        container=container,
    )


@router.get("/source")
async def get_function_source(container: ContainerDep, function_path: str) -> SourceResponse:
    try:
        payload = CodeSourcePayload.model_validate({"function_path": function_path})
    except ValidationError as exc:
        raise_invalid(exc)
    return await op_flows_code_source(
        payload, user=require_context().user, container=container
    )


@router.get("/flow-functions")
async def get_flow_functions(container: ContainerDep, flow_id: str) -> FlowFunctionsResponse:
    return await op_flows_code_flow_functions(
        CodeFlowFunctionsPayload(flow_id=flow_id),
        user=require_context().user,
        container=container,
    )


@router.get("/tool-source")
async def get_tool_source(container: ContainerDep, tool_path: str) -> SourceResponse:
    try:
        payload = CodeToolSourcePayload.model_validate({"tool_path": tool_path})
    except ValidationError as exc:
        raise_invalid(exc)
    return await op_flows_code_tool_source(
        payload, user=require_context().user, container=container
    )


@router.post("/parse-signature", response_model=ParseSignatureResponse)
async def parse_signature(
    container: ContainerDep, request: ParseSignatureRequest
) -> ParseSignatureResponse:
    return await op_flows_code_parse_signature(
        request, user=require_context().user, container=container
    )


@router.post("/validate", response_model=ValidateResponse)
async def validate_code(container: ContainerDep, request: ValidateRequest) -> ValidateResponse:
    return await op_flows_code_validate(
        request, user=require_context().user, container=container
    )


@router.post("/execute", response_model=ExecuteResponse)
async def execute_code(container: ContainerDep, request: ExecuteRequest) -> ExecuteResponse:
    return await op_flows_code_execute(
        request, user=require_context().user, container=container
    )
