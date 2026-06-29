"""
OpenAI-compatible LLM proxy для HumanitecAgent.

Исполнение только через платформенный ``core.ai`` + ``LLMClient`` (биллинг, tracing).
LitServe и прямые provider HTTP clients здесь не используются.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import ClassVar, Literal

from a2a.types import TaskArtifactUpdateEvent, TaskStatusUpdateEvent, TextPart
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict

from apps.agent.device_auth import require_active_device_bearer
from apps.flows.src.dependencies import ContainerDep
from core.ai.models import ResolvedAIModel
from core.ai.providers import (
    HUMANITEC_LLM_AUTO_MODEL,
    HUMANITEC_LLM_PROVIDER,
    PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_SLUGS,
    AICapability,
    humanitec_llms_model_ref,
    split_humanitec_llms_model_ref,
)
from core.ai.requirements import AISelection
from core.ai.resolver import COST_ORIGIN_PLATFORM, resolve_ai_model
from core.ai.runtime import create_llm_client_from_ai_model, should_use_platform_default_free_pool
from core.billing import get_billing_service
from core.billing.exceptions import BillingBalanceBlockedError
from core.billing.service import BALANCE_BLOCK_OPERATION_LLM
from core.clients.llm.context_layer import openai_messages_to_a2a_messages
from core.clients.llm.messages import LLMToolCall
from core.config import get_settings
from core.context import get_context, require_context
from core.logging import get_logger
from core.tracing.tracer import get_tracer
from core.types import JsonArray, JsonObject, JsonValue, require_json_array, require_json_object

logger = get_logger(__name__)
router = APIRouter(tags=["agent-llm-proxy"])

_AGENT_LLM_CONTEXT: JsonObject = {"profile": "off", "budget": "max"}


class AgentOpenAIChatMessage(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")

    role: str
    content: str | JsonArray | None = None
    tool_calls: JsonArray | None = None
    tool_call_id: str | None = None


class AgentOpenAIChatCompletionsRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")

    model: str
    messages: list[AgentOpenAIChatMessage]
    stream: bool | None = False
    temperature: float | None = None
    max_tokens: int | None = None
    tools: JsonArray | None = None


class AgentOpenAIModelItem(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    id: str
    object: Literal["model"] = "model"
    created: int
    owned_by: str = "humanitec"


class AgentOpenAIModelsResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    object: Literal["list"] = "list"
    data: list[AgentOpenAIModelItem]


def _agent_llm_option_value(option: str | JsonObject) -> str | None:
    if isinstance(option, str):
        normalized = option.strip()
        return normalized if normalized else None
    value = option.get("value")
    if isinstance(value, str):
        normalized = value.strip()
        return normalized if normalized else None
    return None


def _resolve_agent_llm_model(requested_model: str) -> ResolvedAIModel:
    if requested_model == HUMANITEC_LLM_AUTO_MODEL:
        resolved = resolve_ai_model(
            AICapability.LLM_CHAT,
            selection=AISelection(
                provider=HUMANITEC_LLM_PROVIDER,
                model=HUMANITEC_LLM_AUTO_MODEL,
            ),
            include_platform_default=False,
        )
        if resolved is None:
            raise HTTPException(
                status_code=503,
                detail="humanitec_llm недоступен для компании",
            )
        return resolved

    parsed_ref = split_humanitec_llms_model_ref(requested_model)
    if parsed_ref is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "model должен быть 'auto' или provider-prefixed "
                + "модель '<provider>:<model_id>'"
            ),
        )
    provider, model_id = parsed_ref
    resolved = resolve_ai_model(
        AICapability.LLM_CHAT,
        selection=AISelection(provider=provider, model=model_id),
        include_platform_default=False,
    )
    if resolved is None:
        raise HTTPException(
            status_code=503,
            detail=f"LLM модель {requested_model!r} недоступна для компании",
        )
    return resolved


async def _read_agent_llm_model_ids(container: ContainerDep) -> list[str]:
    model_ids: list[str] = []
    seen: set[str] = set()

    def append_model_id(model_id: str) -> None:
        if model_id in seen:
            return
        seen.add(model_id)
        model_ids.append(model_id)

    append_model_id(HUMANITEC_LLM_AUTO_MODEL)

    configured_providers = container.llm_models_service.get_configured_providers_by_capability(
        AICapability.LLM_CHAT,
    )
    for provider in configured_providers:
        if provider == HUMANITEC_LLM_PROVIDER:
            continue
        if provider not in PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_SLUGS:
            continue
        catalog_records = await container.ai_model_catalog_repository.list_by_provider_capability(
            provider,
            AICapability.LLM_CHAT,
        )
        for record in catalog_records:
            append_model_id(humanitec_llms_model_ref(record.provider, record.model_id))

    if len(model_ids) == 1:
        humanitec_llm_options = await container.llm_models_service.get_model_ids_by_provider_capability(
            HUMANITEC_LLM_PROVIDER,
            AICapability.LLM_CHAT,
        )
        for option in humanitec_llm_options:
            option_value = _agent_llm_option_value(option)
            if option_value is not None:
                append_model_id(option_value)

    if not model_ids:
        raise HTTPException(
            status_code=503,
            detail="agent LLM model catalog недоступен",
        )
    return model_ids


def _validate_requested_agent_model(requested_model: str, allowed_model_ids: set[str]) -> str:
    normalized = requested_model.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="model обязателен")
    if normalized not in allowed_model_ids:
        raise HTTPException(
            status_code=400,
            detail=f"model {normalized!r} недоступен для HumanitecAgent",
        )
    return normalized


async def _prepare_agent_llm_billing(*, resolved: ResolvedAIModel) -> bool:
    if resolved.model is None:
        raise HTTPException(status_code=503, detail="LLM model не разрешён")
    if resolved.cost_origin == COST_ORIGIN_PLATFORM and should_use_platform_default_free_pool(
        model=resolved.model,
        provider=resolved.provider,
        api_key=resolved.api_key,
        base_url=resolved.base_url,
        folder_id=resolved.folder_id,
        settings=get_settings(),
    ):
        actx = get_context()
        if actx is None or actx.active_company is None:
            raise HTTPException(status_code=500, detail="Context с active_company обязателен")
        return await get_billing_service().company_may_incur_billable_operation_charge(
            actx.active_company.company_id
        )

    actx = get_context()
    if actx is None or actx.active_company is None:
        raise HTTPException(status_code=500, detail="Context с active_company обязателен")
    if not str(actx.user.user_id).strip():
        raise HTTPException(status_code=500, detail="Context с user обязателен")
    await get_billing_service().require_balance_for_billable_operation(
        actx.active_company.company_id,
        str(actx.user.user_id).strip(),
        operation_code=BALANCE_BLOCK_OPERATION_LLM,
        notification_service="flows",
        cost_origin=resolved.cost_origin,
    )
    return True



def _agent_messages_to_openai_json(messages: list[AgentOpenAIChatMessage]) -> list[JsonObject]:
    openai_messages: list[JsonObject] = []
    for message in messages:
        payload: JsonObject = {"role": message.role}
        if message.content is not None:
            payload["content"] = message.content
        if message.tool_calls is not None:
            payload["tool_calls"] = message.tool_calls
        if message.tool_call_id is not None:
            payload["tool_call_id"] = message.tool_call_id
        openai_messages.append(payload)
    return openai_messages


def _tools_schema(tools: JsonArray | None) -> list[JsonObject] | None:
    if tools is None:
        return None
    schema: list[JsonObject] = []
    for tool_item in tools:
        if not isinstance(tool_item, dict):
            continue
        schema.append(require_json_object(tool_item, "agent.llm_proxy.tools[]"))
    return schema if schema else None


def _build_chat_completion_body(
    *,
    completion_id: str,
    model_id: str,
    content: str,
    tool_calls: list[JsonObject] | None,
    finish_reason: str,
) -> JsonObject:
    message_body: JsonObject = {"role": "assistant", "content": content}
    if tool_calls:
        message_body["tool_calls"] = tool_calls
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_id,
        "choices": [
            {
                "index": 0,
                "message": message_body,
                "finish_reason": finish_reason,
            }
        ],
    }


def _build_chat_completion_chunk(
    *,
    completion_id: str,
    model_id: str,
    delta: JsonObject,
    finish_reason: str | None = None,
) -> JsonObject:
    return {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model_id,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
    }


def _sse_line(payload: JsonObject) -> bytes:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")


def _parse_tool_calls(raw_tool_calls: JsonValue | None) -> list[LLMToolCall] | None:
    if raw_tool_calls is None:
        return None
    tool_calls_array = require_json_array(raw_tool_calls, "agent.llm_proxy.tool_calls")
    parsed: list[LLMToolCall] = []
    for tool_call_item in tool_calls_array:
        tool_call_object = require_json_object(tool_call_item, "agent.llm_proxy.tool_call")
        parsed.append(LLMToolCall.model_validate(tool_call_object))
    return parsed if parsed else None


async def _run_agent_llm_call(
    *,
    body: AgentOpenAIChatCompletionsRequest,
    resolved: ResolvedAIModel,
    allow_platform_paid_fallback: bool,
) -> tuple[str, list[JsonObject] | None, int, int, str | None, str | None, str | None]:
    llm = create_llm_client_from_ai_model(
        resolved,
        max_tokens=body.max_tokens,
        temperature=body.temperature,
        allow_platform_paid_fallback=allow_platform_paid_fallback,
    )
    openai_messages = _agent_messages_to_openai_json(body.messages)
    a2a_messages = openai_messages_to_a2a_messages(openai_messages)
    tools_schema = _tools_schema(body.tools)

    tracer = get_tracer()
    llm_provider = llm.llm_provider
    llm_start = time.time()
    content_parts: list[str] = []
    tool_calls_raw: JsonArray = []
    input_tokens = 0
    output_tokens = 0
    resolved_llm_model: str | None = None
    resolved_llm_provider: str | None = None
    resolved_llm_source: str | None = None

    async with tracer.llm_call_span(
        body.model,
        len(a2a_messages),
        len(tools_schema) if tools_schema else 0,
        llm_provider=llm_provider,
    ) as llm_span:
        tracer.record_llm_request(llm_span, openai_messages, tools_schema, None)

        async for event in llm.stream(
            a2a_messages,
            tools=tools_schema,
            max_tokens=body.max_tokens,
            temperature=body.temperature,
            llm_context=_AGENT_LLM_CONTEXT,
        ):
            if isinstance(event, TaskArtifactUpdateEvent):
                if event.artifact and event.artifact.parts:
                    artifact_name = event.artifact.name
                    for part in event.artifact.parts:
                        root = part.root
                        if not isinstance(root, TextPart):
                            continue
                        if artifact_name != "reasoning":
                            content_parts.append(root.text)
            if isinstance(event, TaskStatusUpdateEvent) and event.status:
                if event.status.message and event.status.message.metadata:
                    metadata = require_json_object(
                        event.status.message.metadata,
                        "agent.llm_proxy.status.metadata",
                    )
                    metadata_tool_calls = metadata.get("tool_calls")
                    if metadata_tool_calls:
                        tool_calls_raw = require_json_array(
                            metadata_tool_calls,
                            "agent.llm_proxy.status.metadata.tool_calls",
                        )
                    md_model = metadata.get("model")
                    if isinstance(md_model, str) and md_model.strip():
                        resolved_llm_model = md_model.strip()
                    md_provider = metadata.get("provider")
                    if isinstance(md_provider, str) and md_provider.strip():
                        resolved_llm_provider = md_provider.strip()
                    md_source = metadata.get("source")
                    if isinstance(md_source, str) and md_source.strip():
                        resolved_llm_source = md_source.strip()
                    usage_raw = metadata.get("usage")
                    if isinstance(usage_raw, dict):
                        usage = require_json_object(usage_raw, "agent.llm_proxy.status.metadata.usage")
                        raw_input_tokens = usage.get("input_tokens", 0)
                        raw_output_tokens = usage.get("output_tokens", 0)
                        if isinstance(raw_input_tokens, bool) or not isinstance(raw_input_tokens, int):
                            raise ValueError("usage.input_tokens must be an integer")
                        if isinstance(raw_output_tokens, bool) or not isinstance(raw_output_tokens, int):
                            raise ValueError("usage.output_tokens must be an integer")
                        input_tokens = raw_input_tokens
                        output_tokens = raw_output_tokens

        content = "".join(content_parts)
        parsed_tool_calls = _parse_tool_calls(tool_calls_raw if tool_calls_raw else None)
        tool_calls_json = (
            [
                require_json_object(
                    tool_call.model_dump(mode="json", exclude_none=True),
                    "agent.llm_proxy.tool_call",
                )
                for tool_call in parsed_tool_calls
            ]
            if parsed_tool_calls
            else None
        )
        llm_duration = (time.time() - llm_start) * 1000
        tracer.record_llm_response(
            llm_span,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            has_tool_calls=bool(parsed_tool_calls),
            duration_ms=llm_duration,
            response_content=content,
            tool_calls=tool_calls_json,
            llm_provider=resolved_llm_provider or llm_provider,
            llm_model=resolved_llm_model,
            candidate_source=resolved_llm_source,
            cost_origin=resolved.cost_origin,
        )

    return (
        content,
        tool_calls_json,
        input_tokens,
        output_tokens,
        resolved_llm_provider or llm_provider,
        resolved_llm_model,
        resolved_llm_source,
    )


async def _stream_agent_llm_sse(
    *,
    body: AgentOpenAIChatCompletionsRequest,
    resolved: ResolvedAIModel,
    allow_platform_paid_fallback: bool,
    response_model_id: str,
) -> AsyncIterator[bytes]:
    llm = create_llm_client_from_ai_model(
        resolved,
        max_tokens=body.max_tokens,
        temperature=body.temperature,
        allow_platform_paid_fallback=allow_platform_paid_fallback,
    )
    openai_messages = _agent_messages_to_openai_json(body.messages)
    a2a_messages = openai_messages_to_a2a_messages(openai_messages)
    tools_schema = _tools_schema(body.tools)
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"

    tracer = get_tracer()
    llm_provider = llm.llm_provider
    llm_start = time.time()
    input_tokens = 0
    output_tokens = 0
    resolved_llm_model: str | None = None
    resolved_llm_provider: str | None = None
    resolved_llm_source: str | None = None
    content_parts: list[str] = []
    tool_calls_raw: JsonArray = []

    yield _sse_line(
        _build_chat_completion_chunk(
            completion_id=completion_id,
            model_id=response_model_id,
            delta={"role": "assistant", "content": ""},
        )
    )

    async with tracer.llm_call_span(
        body.model,
        len(a2a_messages),
        len(tools_schema) if tools_schema else 0,
        llm_provider=llm_provider,
    ) as llm_span:
        tracer.record_llm_request(llm_span, openai_messages, tools_schema, None)

        async for event in llm.stream(
            a2a_messages,
            tools=tools_schema,
            max_tokens=body.max_tokens,
            temperature=body.temperature,
            llm_context=_AGENT_LLM_CONTEXT,
        ):
            if isinstance(event, TaskArtifactUpdateEvent):
                if event.artifact and event.artifact.parts:
                    artifact_name = event.artifact.name
                    for part in event.artifact.parts:
                        root = part.root
                        if not isinstance(root, TextPart):
                            continue
                        if artifact_name == "reasoning":
                            continue
                        if root.text:
                            content_parts.append(root.text)
                            yield _sse_line(
                                _build_chat_completion_chunk(
                                    completion_id=completion_id,
                                    model_id=response_model_id,
                                    delta={"content": root.text},
                                )
                            )
            if isinstance(event, TaskStatusUpdateEvent) and event.status:
                if event.status.message and event.status.message.metadata:
                    metadata = require_json_object(
                        event.status.message.metadata,
                        "agent.llm_proxy.stream.metadata",
                    )
                    metadata_tool_calls = metadata.get("tool_calls")
                    if metadata_tool_calls:
                        tool_calls_raw = require_json_array(
                            metadata_tool_calls,
                            "agent.llm_proxy.stream.metadata.tool_calls",
                        )
                    md_model = metadata.get("model")
                    if isinstance(md_model, str) and md_model.strip():
                        resolved_llm_model = md_model.strip()
                    md_provider = metadata.get("provider")
                    if isinstance(md_provider, str) and md_provider.strip():
                        resolved_llm_provider = md_provider.strip()
                    md_source = metadata.get("source")
                    if isinstance(md_source, str) and md_source.strip():
                        resolved_llm_source = md_source.strip()
                    usage_raw = metadata.get("usage")
                    if isinstance(usage_raw, dict):
                        usage = require_json_object(usage_raw, "agent.llm_proxy.stream.metadata.usage")
                        raw_input_tokens = usage.get("input_tokens", 0)
                        raw_output_tokens = usage.get("output_tokens", 0)
                        if isinstance(raw_input_tokens, bool) or not isinstance(raw_input_tokens, int):
                            raise ValueError("usage.input_tokens must be an integer")
                        if isinstance(raw_output_tokens, bool) or not isinstance(raw_output_tokens, int):
                            raise ValueError("usage.output_tokens must be an integer")
                        input_tokens = raw_input_tokens
                        output_tokens = raw_output_tokens

        parsed_tool_calls = _parse_tool_calls(tool_calls_raw if tool_calls_raw else None)
        tool_calls_json = (
            [
                require_json_object(
                    tool_call.model_dump(mode="json", exclude_none=True),
                    "agent.llm_proxy.stream.tool_call",
                )
                for tool_call in parsed_tool_calls
            ]
            if parsed_tool_calls
            else None
        )
        finish_reason = "tool_calls" if tool_calls_json else "stop"
        if tool_calls_json:
            yield _sse_line(
                _build_chat_completion_chunk(
                    completion_id=completion_id,
                    model_id=response_model_id,
                    delta={"tool_calls": tool_calls_json},
                )
            )

        llm_duration = (time.time() - llm_start) * 1000
        tracer.record_llm_response(
            llm_span,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            has_tool_calls=bool(parsed_tool_calls),
            duration_ms=llm_duration,
            response_content="".join(content_parts),
            tool_calls=tool_calls_json,
            llm_provider=resolved_llm_provider or llm_provider,
            llm_model=resolved_llm_model,
            candidate_source=resolved_llm_source,
            cost_origin=resolved.cost_origin,
        )

    yield _sse_line(
        _build_chat_completion_chunk(
            completion_id=completion_id,
            model_id=response_model_id,
            delta={},
            finish_reason=finish_reason,
        )
    )
    yield b"data: [DONE]\n\n"


@router.get("/agent/llm/v1/models", tags=["agent-llm-proxy", "public"])
async def agent_llm_models(
    request: Request,
    container: ContainerDep,
) -> AgentOpenAIModelsResponse:
    await require_active_device_bearer(request, container)
    _ = require_context()
    model_ids = await _read_agent_llm_model_ids(container)
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
    container: ContainerDep,
) -> JSONResponse | StreamingResponse:
    await require_active_device_bearer(request, container)
    _ = require_context()

    if not body.messages:
        raise HTTPException(status_code=400, detail="messages обязателен")

    model_ids = await _read_agent_llm_model_ids(container)
    requested_model = _validate_requested_agent_model(body.model, set(model_ids))
    resolved = _resolve_agent_llm_model(requested_model)
    try:
        allow_platform_paid_fallback = await _prepare_agent_llm_billing(resolved=resolved)
    except BillingBalanceBlockedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    response_model_id = requested_model
    logger.info(
        "agent.llm_proxy.request",
        requested_model=body.model,
        stream=bool(body.stream),
        messages_count=len(body.messages),
    )

    if body.stream:
        return StreamingResponse(
            _stream_agent_llm_sse(
                body=body,
                resolved=resolved,
                allow_platform_paid_fallback=allow_platform_paid_fallback,
                response_model_id=response_model_id,
            ),
            media_type="text/event-stream",
        )

    (
        content,
        tool_calls_json,
        _input_tokens,
        _output_tokens,
        _provider,
        _model,
        _source,
    ) = await _run_agent_llm_call(
        body=body,
        resolved=resolved,
        allow_platform_paid_fallback=allow_platform_paid_fallback,
    )
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    finish_reason = "tool_calls" if tool_calls_json else "stop"
    return JSONResponse(
        _build_chat_completion_body(
            completion_id=completion_id,
            model_id=response_model_id,
            content=content,
            tool_calls=tool_calls_json,
            finish_reason=finish_reason,
        )
    )
