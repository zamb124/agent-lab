"""HTTP-граница OpenAI-compatible LLM proxy."""

import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from apps.flows.di import Di
from apps.flows.src.agent.llm_auth import LlmProxyAuthResult, require_llm_proxy_auth
from apps.flows.src.agent.llm_proxy import (
    AgentOpenAIChatCompletionsRequest,
    AgentOpenAIImagesGenerationsRequest,
    AgentOpenAIModelItem,
    AgentOpenAIModelsResponse,
    OnlyOfficeLlmProxyEnvelope,
    dispatch_chat_completions,
    dispatch_images_generations,
    proxy_target_path,
    read_agent_llm_model_ids,
)
from core.context import require_context
from core.logging import get_logger
from core.types import JsonObject, parse_json_object, require_json_object
from core.websocket import WsCommandError

logger = get_logger(__name__)
router = APIRouter(tags=["agent-llm-proxy"])


async def _run_chat_completions(
    body: AgentOpenAIChatCompletionsRequest,
    auth: LlmProxyAuthResult,
    di: Di,
) -> JSONResponse | StreamingResponse:
    return await dispatch_chat_completions(
        body=body,
        auth=auth,
        llm_models_service=di.llm_models_service,
        variables_service=di.variables_service,
        authz_service=di.authz_service,
        workflow_runtime=di.workflow_runtime,
        redis_client=di.redis_client,
        handoff_orchestrator_service=di.handoff_orchestrator_service,
        flow_factory=di.flow_factory,
        tool_registry=di.tool_registry,
        projection_service=di.a2a_task_projection_service,
        shared_storage=di.shared_storage,
        channel_registry=di.channel_registry,
        mail_service=di.mail_service,
        flow_ui_share_service=di.flow_ui_share_service,
        hitl_conversation_service=di.hitl_conversation_service,
        files_service=di.files_service,
    )


@router.get("/agent/llm/v1/models", tags=["agent-llm-proxy", "public"])
async def agent_llm_models(
    request: Request,
    di: Di,
) -> AgentOpenAIModelsResponse:
    _ = await require_llm_proxy_auth(request, di.shared_storage)
    _ = require_context()
    model_ids = await read_agent_llm_model_ids(di.llm_models_service)
    created_at = int(time.time())
    return AgentOpenAIModelsResponse(
        data=[
            AgentOpenAIModelItem(
                id=model_id,
                created=created_at,
            )
            for model_id in model_ids
        ]
    )


@router.post(
    "/agent/llm/v1/chat/completions",
    tags=["agent-llm-proxy", "public"],
    response_model=None,
)
async def agent_llm_chat_completions(
    body: AgentOpenAIChatCompletionsRequest,
    request: Request,
    di: Di,
) -> JSONResponse | StreamingResponse:
    auth = await require_llm_proxy_auth(request, di.shared_storage)
    _ = require_context()
    return await _run_chat_completions(body, auth, di)


@router.post(
    "/agent/llm/v1/images/generations",
    tags=["agent-llm-proxy", "public"],
    response_model=None,
)
async def agent_llm_images_generations(
    body: AgentOpenAIImagesGenerationsRequest,
    request: Request,
    di: Di,
) -> JSONResponse:
    _ = await require_llm_proxy_auth(request, di.shared_storage)
    _ = require_context()
    return await dispatch_images_generations(body=body, shared_storage=di.shared_storage)


@router.post(
    "/agent/llm/v1/proxy",
    tags=["agent-llm-proxy", "public"],
    response_model=None,
)
async def agent_llm_onlyoffice_proxy(
    envelope: OnlyOfficeLlmProxyEnvelope,
    request: Request,
    di: Di,
) -> JSONResponse | StreamingResponse | Response:
    """Unwrap OnlyOffice AI ``{target,method,headers,data}`` → OpenAI handlers."""
    auth = await require_llm_proxy_auth(request, di.shared_storage)
    _ = require_context()
    method = envelope.method.strip().upper()
    if method not in {"GET", "POST"}:
        raise WsCommandError(
            "ws_invalid_payload",
            f"proxy method {method!r} is not supported",
            error_code="llm_proxy_method_unsupported",
            error_params={"method": method},
        )

    relative = proxy_target_path(envelope.target)
    logger.info(
        "agent.llm_proxy.onlyoffice_proxy",
        target_path=relative,
        method=method,
        auth_kind=auth.kind,
    )

    if relative == "models":
        if method != "GET":
            raise WsCommandError(
                "method_not_allowed",
                "models accepts GET only",
                error_code="llm_proxy_models_get_only",
            )
        model_ids = await read_agent_llm_model_ids(di.llm_models_service)
        created_at = int(time.time())
        return JSONResponse(
            AgentOpenAIModelsResponse(
                data=[
                    AgentOpenAIModelItem(id=model_id, created=created_at)
                    for model_id in model_ids
                ]
            ).model_dump(mode="json")
        )

    raw_data = envelope.data
    payload: JsonObject
    if isinstance(raw_data, str):
        if not raw_data.strip():
            payload = {}
        else:
            try:
                payload = parse_json_object(raw_data, "onlyoffice.proxy.data")
            except ValueError as exc:
                raise WsCommandError(
                    "ws_invalid_payload",
                    "proxy.data must be a JSON object",
                    error_code="llm_proxy_data_invalid",
                ) from exc
    elif isinstance(raw_data, dict):
        payload = require_json_object(raw_data, "onlyoffice.proxy.data")
    elif raw_data is None:
        payload = {}
    else:
        raise WsCommandError(
            "ws_invalid_payload",
            "proxy.data must be a JSON object or string",
            error_code="llm_proxy_data_invalid",
        )

    if relative == "chat/completions":
        if method != "POST":
            raise WsCommandError(
                "method_not_allowed",
                "chat/completions accepts POST only",
                error_code="llm_proxy_chat_post_only",
            )
        body = AgentOpenAIChatCompletionsRequest.model_validate(payload)
        return await _run_chat_completions(body, auth, di)

    if relative == "images/generations":
        if method != "POST":
            raise WsCommandError(
                "method_not_allowed",
                "images/generations accepts POST only",
                error_code="llm_proxy_images_post_only",
            )
        images_body = AgentOpenAIImagesGenerationsRequest.model_validate(payload)
        return await dispatch_images_generations(
            body=images_body,
            shared_storage=di.shared_storage,
        )

    raise WsCommandError(
        "not_found",
        f"proxy target path {relative!r} not found",
        error_code="llm_proxy_target_not_found",
        error_params={"path": relative},
    )
