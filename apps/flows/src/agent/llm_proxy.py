"""
OpenAI-compatible LLM proxy для LinnexAgent и OnlyOffice AI.

Тонкий HTTP adapter: parse OpenAI request → route → LLMClient / Lara A2A / NanoBanana
→ OpenAI response codec. Execution-логика (messages, tools, LLM fallback chain,
billing spans) — только в ``LLMClient`` / ``core.ai``.
"""

from __future__ import annotations

import base64
import json
import os
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import ClassVar, Literal
from urllib.parse import urlparse

from a2a.types import TaskArtifactUpdateEvent, TaskStatusUpdateEvent
from fastapi import HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import Response as StarletteResponse
from starlette.types import ExceptionHandler

from apps.flows.src.a2a.task_projection_service import A2ATaskProjectionService
from apps.flows.src.agent.llm_auth import LlmProxyAuthResult
from apps.flows.src.agent.llm_lara import (
    list_lara_branch_model_ids,
    load_lara_branch_ids,
    run_lara_chat_completion,
)
from apps.flows.src.channels.factory import get_channel
from apps.flows.src.contracts import (
    ChannelRegistryProtocol,
    FlowFactoryProtocol,
    ToolRegistryProtocol,
)
from apps.flows.src.durable_execution.manager import DurableWorkflowRuntime
from apps.flows.src.services.flow_ui_share_service import FlowUIShareService
from apps.flows.src.services.handoff_orchestrator_service import HandoffOrchestratorService
from apps.flows.src.services.hitl_conversation_service import HitlConversationService
from core.a2a import (
    coerce_usage_token_count,
    get_part_text,
    mapping_from_struct,
    part_has_text,
)
from core.ai.llm_models_service import LLMModelsService
from core.ai.models import AIModelRecord, ResolvedAIModel
from core.ai.provider_error import AIProviderErrorClass, classify_ai_provider_error
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
from core.ai.runtime import create_llm_client_from_ai_model
from core.authz.service import AuthzService
from core.billing.exceptions import BillingBalanceBlockedError
from core.clients.llm.client import LLMClient
from core.clients.llm.context_layer import openai_messages_to_a2a_messages
from core.clients.llm.messages import LLMToolCall
from core.clients.llm.mock import MockLLM
from core.clients.llm.openai_api_codec import (
    build_chat_completion,
    build_chat_completion_chunk,
    build_chat_completion_usage_chunk,
    build_openai_usage,
    new_chat_completion_id,
    openai_error_body,
    sse_data_line,
    sse_done_line,
)
from core.clients.nano_banana import NanoBananaClient
from core.clients.redis_client import RedisClient
from core.context import get_context
from core.db.storage import SharedStorage
from core.files.models import FileRecord
from core.files.object_store.gate import FileGate
from core.files.object_store.principals import SystemPrincipal
from core.files.service import FilesService
from core.logging import get_logger
from core.mail.service import MailService
from core.office.ai_settings import (
    IMAGE_AUTO_MODEL_ID,
    LARA_MODEL_PREFIX,
    parse_lara_branch_model_id,
)
from core.types import (
    JsonArray,
    JsonObject,
    JsonValue,
    require_json_array,
    require_json_object,
)
from core.variables.service import VariablesService
from core.websocket import WsCommandError, command_failure_payload
from core.websocket.operation import ws_command_error_status

logger = get_logger(__name__)

AGENT_LLM_PROXY_USE_MOCK_AUTO_ENV = "AGENT_LLM_PROXY_USE_MOCK_AUTO"
_LLM_PROXY_PATH_PREFIX = "/flows/api/v1/agent/llm/"


class AgentOpenAIChatMessage(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")

    role: str
    content: str | JsonArray | None = None
    tool_calls: JsonArray | None = None
    tool_call_id: str | None = None
    name: str | None = None


class AgentOpenAIChatCompletionsRequest(BaseModel):
    """Подмножество OpenRouter/OpenAI ChatRequest; unknown OR fields игнорируются."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")

    model: str
    messages: list[AgentOpenAIChatMessage]
    stream: bool | None = False
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    seed: int | None = None
    tools: JsonArray | None = None
    tool_choice: str | JsonObject | None = None
    response_format: JsonObject | None = None
    n: int | None = None


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


class AgentOpenAIImagesGenerationsRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")

    model: str = IMAGE_AUTO_MODEL_ID
    prompt: str = Field(min_length=1)
    n: int | None = 1
    size: str | None = None
    response_format: Literal["url", "b64_json"] | None = "b64_json"


class OnlyOfficeLlmProxyEnvelope(BaseModel):
    """Тело OnlyOffice AI plugin proxy: unwrap → target OpenAI path."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")

    target: str = Field(min_length=1)
    method: str = Field(min_length=1)
    headers: dict[str, str] | None = None
    data: str | JsonObject | None = None


def _openai_error_type_for_status(status_code: int) -> str:
    if status_code == 401:
        return "authentication_error"
    if status_code == 403:
        return "permission_error"
    if status_code == 429:
        return "rate_limit_error"
    if status_code >= 500:
        return "api_error"
    return "invalid_request_error"


def _http_exception_message(detail: object) -> str:
    if isinstance(detail, str):
        return detail
    return json.dumps(detail, ensure_ascii=False)


async def _llm_proxy_http_exception_handler(
    request: Request,
    exc: Exception,
) -> StarletteResponse:
    if not isinstance(exc, HTTPException):
        raise exc
    if not request.url.path.startswith(_LLM_PROXY_PATH_PREFIX):
        return await http_exception_handler(request, exc)
    headers = exc.headers
    return JSONResponse(
        status_code=exc.status_code,
        content=openai_error_body(
            message=_http_exception_message(exc.detail),
            error_type=_openai_error_type_for_status(exc.status_code),
            code=str(exc.status_code),
        ),
        headers=dict(headers) if headers is not None else None,
    )


async def _llm_proxy_ws_command_error_handler(
    request: Request,
    exc: Exception,
) -> StarletteResponse:
    if not isinstance(exc, WsCommandError):
        raise exc
    status_code = ws_command_error_status(exc)
    if not request.url.path.startswith(_LLM_PROXY_PATH_PREFIX):
        return JSONResponse(status_code=status_code, content=command_failure_payload(exc))
    return JSONResponse(
        status_code=status_code,
        content=openai_error_body(
            message=exc.detail,
            error_type=_openai_error_type_for_status(status_code),
            code=exc.error_code,
        ),
    )


# OpenAI/OR error envelope ``{"error":{message,type,code}}`` для LLM proxy surface —
# внешняя wire-спека, подключается через `create_service_app(extra_exception_handlers=...)`.
LLM_PROXY_EXCEPTION_HANDLERS: tuple[tuple[type[Exception], ExceptionHandler], ...] = (
    (WsCommandError, _llm_proxy_ws_command_error_handler),
    (HTTPException, _llm_proxy_http_exception_handler),
)


def _agent_llm_option_value(option: str | JsonObject) -> str | None:
    if isinstance(option, str):
        normalized = option.strip()
        return normalized if normalized else None
    value = option.get("value")
    if isinstance(value, str):
        normalized = value.strip()
        return normalized if normalized else None
    return None


def _resolve_agent_llm_auto_mock_bridge(requested_model: str) -> ResolvedAIModel | None:
    """Узкий testing-bridge: auto → mock только при AGENT_LLM_PROXY_USE_MOCK_AUTO=1 (стек E2E)."""
    if requested_model != HUMANITEC_LLM_AUTO_MODEL:
        return None
    if os.environ.get(AGENT_LLM_PROXY_USE_MOCK_AUTO_ENV) != "1":
        return None
    return resolve_ai_model(
        AICapability.LLM_CHAT,
        selection=AISelection(provider="mock", model="mock-gpt-4"),
        include_platform_default=False,
    )


def _resolve_agent_llm_model(requested_model: str) -> ResolvedAIModel:
    bridged = _resolve_agent_llm_auto_mock_bridge(requested_model)
    if bridged is not None:
        return bridged
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
            raise WsCommandError(
                "unavailable",
                "humanitec_llm is unavailable for the company",
                error_code="humanitec_llm_unavailable",
            )
        return resolved

    if requested_model == IMAGE_AUTO_MODEL_ID:
        raise WsCommandError(
            "ws_invalid_payload",
            "model 'image-auto' is only available via /images/generations",
            error_code="image_auto_wrong_endpoint",
        )

    if parse_lara_branch_model_id(requested_model) is not None:
        raise WsCommandError(
            "ws_invalid_payload",
            "lara:<branch> is handled by a separate A2A bridge",
            error_code="lara_model_wrong_path",
        )

    parsed_ref = split_humanitec_llms_model_ref(requested_model)
    if parsed_ref is None:
        raise WsCommandError(
            "ws_invalid_payload",
            "model must be 'auto', 'lara:<branch>', 'image-auto' or '<provider>:<model_id>'",
            error_code="agent_llm_model_invalid",
        )
    provider, model_id = parsed_ref
    resolved = resolve_ai_model(
        AICapability.LLM_CHAT,
        selection=AISelection(provider=provider, model=model_id),
        include_platform_default=False,
    )
    if resolved is None:
        raise WsCommandError(
            "unavailable",
            f"LLM model {requested_model!r} is unavailable for the company",
            error_code="agent_llm_model_unavailable",
            error_params={"model": requested_model},
        )
    return resolved


async def read_agent_llm_model_ids(llm_models_service: LLMModelsService) -> list[str]:
    model_ids: list[str] = []
    seen: set[str] = set()

    def append_model_id(model_id: str) -> None:
        if model_id in seen:
            return
        seen.add(model_id)
        model_ids.append(model_id)

    append_model_id(HUMANITEC_LLM_AUTO_MODEL)
    append_model_id(IMAGE_AUTO_MODEL_ID)

    lara_branches = await load_lara_branch_ids()
    for lara_model_id in list_lara_branch_model_ids(lara_branches):
        append_model_id(lara_model_id)

    configured_providers = llm_models_service.get_configured_providers_by_capability(
        AICapability.LLM_CHAT,
    )
    for provider in configured_providers:
        if provider == HUMANITEC_LLM_PROVIDER:
            continue
        if provider not in PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_SLUGS:
            continue
        catalog_records = await AIModelRecord.list_by_provider_capability(
            provider,
            AICapability.LLM_CHAT,
        )
        for record in catalog_records:
            append_model_id(humanitec_llms_model_ref(record.provider, record.model_id))

    if len(model_ids) == 2 + len(lara_branches):
        humanitec_llm_options = await llm_models_service.get_model_ids_by_provider_capability(
            HUMANITEC_LLM_PROVIDER,
            AICapability.LLM_CHAT,
        )
        for option in humanitec_llm_options:
            option_value = _agent_llm_option_value(option)
            if option_value is not None:
                append_model_id(option_value)

    if not model_ids:
        raise WsCommandError(
            "unavailable",
            "agent LLM model catalog is unavailable",
            error_code="agent_llm_catalog_unavailable",
        )
    return model_ids


def _validate_requested_agent_model(requested_model: str, allowed_model_ids: set[str]) -> str:
    normalized = requested_model.strip()
    if not normalized:
        raise WsCommandError(
            "ws_invalid_payload",
            "model is required",
            error_code="agent_llm_model_required",
        )
    if normalized.startswith(LARA_MODEL_PREFIX) and parse_lara_branch_model_id(normalized) is None:
        raise WsCommandError(
            "ws_invalid_payload",
            "lara:<branch_id> requires a non-empty branch_id",
            error_code="lara_branch_id_required",
        )
    if normalized not in allowed_model_ids:
        raise WsCommandError(
            "ws_invalid_payload",
            f"model {normalized!r} is not available for LLM proxy",
            error_code="agent_llm_model_not_allowed",
            error_params={"model": normalized},
        )
    return normalized


async def _prepare_agent_llm_client(
    *,
    body: AgentOpenAIChatCompletionsRequest,
    resolved: ResolvedAIModel,
) -> LLMClient | MockLLM:
    llm = create_llm_client_from_ai_model(
        resolved,
        max_tokens=body.max_tokens,
        temperature=body.temperature,
        top_p=body.top_p,
        frequency_penalty=body.frequency_penalty,
        presence_penalty=body.presence_penalty,
        seed=body.seed,
    )
    if isinstance(llm, LLMClient):
        try:
            _ = await llm.prepare_billing()
        except BillingBalanceBlockedError as exc:
            raise WsCommandError(
                "forbidden",
                str(exc),
                error_code="billing_balance_blocked",
            ) from exc
    return llm


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
        if message.name is not None:
            payload["name"] = message.name
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


def _stream_extra_body(body: AgentOpenAIChatCompletionsRequest) -> JsonObject | None:
    if body.tool_choice is None:
        return None
    return {"tool_choice": body.tool_choice}


def _build_usage_payload(
    *,
    input_tokens: int,
    output_tokens: int,
    cost_origin: str,
) -> JsonObject:
    cost = 0.0 if cost_origin == COST_ORIGIN_PLATFORM else None
    return build_openai_usage(
        prompt_tokens=input_tokens,
        completion_tokens=output_tokens,
        cost=cost,
    )


def _parse_tool_calls(raw_tool_calls: JsonValue | None) -> list[LLMToolCall] | None:
    if raw_tool_calls is None:
        return None
    tool_calls_array = require_json_array(raw_tool_calls, "agent.llm_proxy.tool_calls")
    parsed: list[LLMToolCall] = []
    for tool_call_item in tool_calls_array:
        tool_call_object = require_json_object(tool_call_item, "agent.llm_proxy.tool_call")
        parsed.append(LLMToolCall.model_validate(tool_call_object))
    return parsed if parsed else None


@dataclass
class _AgentLlmCallState:
    content_parts: list[str] = field(default_factory=list)
    tool_calls_raw: JsonArray = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    resolved_llm_model: str | None = None
    resolved_llm_provider: str | None = None
    resolved_llm_source: str | None = None
    stream_error: Exception | None = None

    @property
    def content(self) -> str:
        return "".join(self.content_parts)

    def tool_calls_json(self) -> list[JsonObject] | None:
        parsed = _parse_tool_calls(self.tool_calls_raw if self.tool_calls_raw else None)
        if not parsed:
            return None
        return [
            require_json_object(
                tool_call.model_dump(mode="json", exclude_none=True),
                "agent.llm_proxy.tool_call",
            )
            for tool_call in parsed
        ]


def _require_agent_error_provider(provider: str | None) -> str:
    if provider is None or not provider.strip():
        raise ValueError("agent llm_proxy: provider is required for error classification")
    return provider


def _agent_error_provider(state: _AgentLlmCallState, fallback_provider: str | None) -> str:
    runtime_provider = state.resolved_llm_provider
    if runtime_provider is not None and runtime_provider.strip():
        return runtime_provider
    return _require_agent_error_provider(fallback_provider)


def _agent_pool_exhausted(exc: Exception) -> bool:
    if not isinstance(exc, RuntimeError):
        return False
    error_text = str(exc).lower()
    return (
        "cooldown" in error_text
        or "нет доступных" in error_text
        or "free-pool" in error_text
    )


def _is_rate_limit_error(exc: Exception, *, provider: str) -> bool:
    if _agent_pool_exhausted(exc):
        return True
    record = classify_ai_provider_error(provider, exc)
    return record.error_class == AIProviderErrorClass.RATE_LIMITED


def _agent_llm_error_message(exc: Exception, model: str, *, provider: str) -> str:
    if _is_rate_limit_error(exc, provider=provider):
        return (
            f"Превышен лимит запросов для модели {model}. "
            "Попробуйте позже или выберите модель auto."
        )
    return "Модель временно недоступна, попробуйте ещё раз или смените модель."


def _apply_status_metadata(state: _AgentLlmCallState, metadata: JsonObject) -> None:
    metadata_tool_calls = metadata.get("tool_calls")
    if metadata_tool_calls:
        state.tool_calls_raw = require_json_array(
            metadata_tool_calls,
            "agent.llm_proxy.status.metadata.tool_calls",
        )
    md_model = metadata.get("model")
    if isinstance(md_model, str) and md_model.strip():
        state.resolved_llm_model = md_model.strip()
    md_provider = metadata.get("provider")
    if isinstance(md_provider, str) and md_provider.strip():
        state.resolved_llm_provider = md_provider.strip()
    md_source = metadata.get("source")
    if isinstance(md_source, str) and md_source.strip():
        state.resolved_llm_source = md_source.strip()
    usage_raw = metadata.get("usage")
    if isinstance(usage_raw, dict):
        usage = require_json_object(usage_raw, "agent.llm_proxy.status.metadata.usage")
        state.input_tokens = coerce_usage_token_count(
            usage.get("input_tokens", 0),
            "usage.input_tokens",
        )
        state.output_tokens = coerce_usage_token_count(
            usage.get("output_tokens", 0),
            "usage.output_tokens",
        )


async def _iter_agent_llm_content_deltas(
    *,
    body: AgentOpenAIChatCompletionsRequest,
    llm: LLMClient | MockLLM,
) -> AsyncIterator[str | _AgentLlmCallState]:
    """
    Единый путь LLMClient.stream: yield content deltas, финальный yield — состояние вызова.

    Platform LLM context layer не включается (``llm_context=None``) — Goose/OO passthrough.
    """
    openai_messages = _agent_messages_to_openai_json(body.messages)
    a2a_messages = openai_messages_to_a2a_messages(openai_messages)
    tools_schema = _tools_schema(body.tools)
    extra_body = _stream_extra_body(body)
    state = _AgentLlmCallState()

    try:
        async for event in llm.stream(
            a2a_messages,
            tools=tools_schema,
            max_tokens=body.max_tokens,
            temperature=body.temperature,
            top_p=body.top_p,
            frequency_penalty=body.frequency_penalty,
            presence_penalty=body.presence_penalty,
            seed=body.seed,
            response_format=body.response_format,
            extra_body=extra_body,
            llm_context=None,
        ):
            if isinstance(event, TaskArtifactUpdateEvent):
                if event.HasField("artifact") and event.artifact.parts:
                    artifact_name = event.artifact.name
                    for part in event.artifact.parts:
                        if not part_has_text(part):
                            continue
                        if artifact_name == "reasoning":
                            continue
                        text = get_part_text(part)
                        if text:
                            state.content_parts.append(text)
                            yield text
            if isinstance(event, TaskStatusUpdateEvent) and event.HasField("status"):
                if event.status.HasField("message") and event.status.message.HasField(
                    "metadata"
                ):
                    metadata = mapping_from_struct(event.status.message.metadata)
                    _apply_status_metadata(state, metadata)
    except Exception as exc:
        state.stream_error = exc
        logger.warning(
            "agent.llm_proxy.stream_failed",
            requested_model=body.model,
            error=str(exc),
            error_type=type(exc).__name__,
        )

    yield state


async def _run_agent_llm_call(
    *,
    body: AgentOpenAIChatCompletionsRequest,
    llm: LLMClient | MockLLM,
) -> tuple[str, list[JsonObject] | None, int, int, str | None, str | None, str | None]:
    state: _AgentLlmCallState | None = None
    async for item in _iter_agent_llm_content_deltas(
        body=body,
        llm=llm,
    ):
        if isinstance(item, _AgentLlmCallState):
            state = item
    if state is None:
        raise RuntimeError("agent LLM call produced no final state")
    if state.stream_error is not None:
        raise state.stream_error
    return (
        state.content,
        state.tool_calls_json(),
        state.input_tokens,
        state.output_tokens,
        state.resolved_llm_provider,
        state.resolved_llm_model,
        state.resolved_llm_source,
    )


async def _stream_agent_llm_sse(
    *,
    body: AgentOpenAIChatCompletionsRequest,
    llm: LLMClient | MockLLM,
    response_model_id: str,
) -> AsyncIterator[bytes]:
    completion_id = new_chat_completion_id()
    yield sse_data_line(
        build_chat_completion_chunk(
            completion_id=completion_id,
            model_id=response_model_id,
            delta={"role": "assistant", "content": ""},
        )
    )

    state: _AgentLlmCallState | None = None
    async for item in _iter_agent_llm_content_deltas(
        body=body,
        llm=llm,
    ):
        if isinstance(item, str):
            yield sse_data_line(
                build_chat_completion_chunk(
                    completion_id=completion_id,
                    model_id=response_model_id,
                    delta={"content": item},
                )
            )
        else:
            state = item

    if state is None:
        raise RuntimeError("agent LLM stream produced no final state")

    tool_calls_json = state.tool_calls_json()
    finish_reason = "tool_calls" if tool_calls_json else "stop"

    if state.stream_error is not None:
        finish_reason = "stop"
        yield sse_data_line(
            build_chat_completion_chunk(
                completion_id=completion_id,
                model_id=response_model_id,
                delta={
                    "content": _agent_llm_error_message(
                        state.stream_error,
                        response_model_id,
                        provider=_agent_error_provider(state, llm.llm_provider),
                    ),
                },
            )
        )
    elif tool_calls_json:
        yield sse_data_line(
            build_chat_completion_chunk(
                completion_id=completion_id,
                model_id=response_model_id,
                delta={"tool_calls": tool_calls_json},
            )
        )
    elif not state.content_parts:
        yield sse_data_line(
            build_chat_completion_chunk(
                completion_id=completion_id,
                model_id=response_model_id,
                delta={
                    "content": (
                        "Модель не вернула ответ. Попробуйте ещё раз или смените модель."
                    ),
                },
            )
        )

    yield sse_data_line(
        build_chat_completion_usage_chunk(
            completion_id=completion_id,
            model_id=response_model_id,
            usage=_build_usage_payload(
                input_tokens=state.input_tokens,
                output_tokens=state.output_tokens,
                cost_origin=(
                    llm.billing.cost_origin
                    if isinstance(llm, LLMClient)
                    else COST_ORIGIN_PLATFORM
                ),
            ),
        )
    )
    yield sse_data_line(
        build_chat_completion_chunk(
            completion_id=completion_id,
            model_id=response_model_id,
            delta={},
            finish_reason=finish_reason,
        )
    )
    yield sse_done_line()


def _openai_messages_from_body(body: AgentOpenAIChatCompletionsRequest) -> list[JsonObject]:
    return _agent_messages_to_openai_json(body.messages)


async def _stream_lara_sse(*, model_id: str, content: str) -> AsyncIterator[bytes]:
    completion_id = new_chat_completion_id()
    yield sse_data_line(
        build_chat_completion_chunk(
            completion_id=completion_id,
            model_id=model_id,
            delta={"role": "assistant", "content": content},
            finish_reason=None,
        )
    )
    yield sse_data_line(
        build_chat_completion_chunk(
            completion_id=completion_id,
            model_id=model_id,
            delta={},
            finish_reason="stop",
        )
    )
    yield sse_done_line()


async def _file_id_to_b64_json(shared_storage: SharedStorage, file_id: str) -> str:
    file_payload = await shared_storage.get(f"file:{file_id}")
    if file_payload is None:
        raise WsCommandError(
            "upstream",
            f"generated file {file_id} not found",
            error_code="generated_file_not_found",
            error_params={"file_id": file_id},
        )
    file_record = FileRecord.model_validate_json(file_payload)
    if file_record.company_id is None or file_record.company_id == "":
        raise WsCommandError(
            "upstream",
            f"generated file {file_id} has no company_id",
            error_code="generated_file_not_found",
            error_params={"file_id": file_id},
        )
    handle = await FileGate().open_record(
        file_record,
        SystemPrincipal(company_id=file_record.company_id),
    )
    file_bytes = await handle.read_bytes()
    if not file_bytes:
        raise WsCommandError(
            "upstream",
            f"file {file_id} is empty",
            error_code="generated_file_empty",
            error_params={"file_id": file_id},
        )
    return base64.b64encode(file_bytes).decode("ascii")


def proxy_target_path(target: str) -> str:
    parsed = urlparse(target.strip())
    path = parsed.path if parsed.scheme else target.strip()
    if not path.startswith("/"):
        path = f"/{path}"
    marker = "/agent/llm/v1/"
    idx = path.find(marker)
    if idx < 0:
        raise WsCommandError(
            "ws_invalid_payload",
            "proxy target must point to /flows/api/v1/agent/llm/v1/…",
            error_code="llm_proxy_target_invalid",
        )
    return path[idx + len(marker) :].strip("/")


def _validate_chat_request_n(body: AgentOpenAIChatCompletionsRequest) -> None:
    if body.n is None or body.n == 1:
        return
    raise WsCommandError(
        "ws_invalid_payload",
        "n > 1 is not supported by LLM proxy",
        error_code="llm_proxy_n_unsupported",
    )


async def dispatch_chat_completions(
    *,
    body: AgentOpenAIChatCompletionsRequest,
    auth: LlmProxyAuthResult,
    llm_models_service: LLMModelsService,
    variables_service: VariablesService,
    authz_service: AuthzService,
    workflow_runtime: DurableWorkflowRuntime,
    redis_client: RedisClient,
    handoff_orchestrator_service: HandoffOrchestratorService,
    flow_factory: FlowFactoryProtocol,
    tool_registry: ToolRegistryProtocol,
    projection_service: A2ATaskProjectionService,
    shared_storage: SharedStorage,
    channel_registry: ChannelRegistryProtocol,
    mail_service: MailService,
    flow_ui_share_service: FlowUIShareService,
    hitl_conversation_service: HitlConversationService,
    files_service: FilesService,
) -> JSONResponse | StreamingResponse:
    if not body.messages:
        raise WsCommandError(
            "ws_invalid_payload",
            "messages is required",
            error_code="llm_proxy_messages_required",
        )
    _validate_chat_request_n(body)

    model_ids = await read_agent_llm_model_ids(llm_models_service)
    requested_model = _validate_requested_agent_model(body.model, set(model_ids))
    logger.info(
        "agent.llm_proxy.request",
        requested_model=body.model,
        stream=bool(body.stream),
        messages_count=len(body.messages),
        auth_kind=auth.kind,
    )

    lara_branch = parse_lara_branch_model_id(requested_model)
    if lara_branch is not None:
        context = get_context()
        if context is None:
            raise WsCommandError(
                "unauthorized",
                "context is not set",
                error_code="context_not_set",
            )
        channel = get_channel(
            "a2a",
            "lara",
            context,
            variables_service=variables_service,
            authz_service=authz_service,
            workflow_runtime=workflow_runtime,
            redis_client=redis_client,
            handoff_orchestrator_service=handoff_orchestrator_service,
            flow_factory=flow_factory,
            tool_registry=tool_registry,
            projection_service=projection_service,
            shared_storage=shared_storage,
            channel_registry=channel_registry,
            mail_service=mail_service,
            flow_ui_share_service=flow_ui_share_service,
            hitl_conversation_service=hitl_conversation_service,
            files_service=files_service,
        )
        content = await run_lara_chat_completion(
            channel,
            model_id=requested_model,
            openai_messages=_openai_messages_from_body(body),
            office_ai=auth.office_ai,
        )
        if body.stream:
            return StreamingResponse(
                _stream_lara_sse(model_id=requested_model, content=content),
                media_type="text/event-stream",
            )
        return JSONResponse(
            build_chat_completion(
                completion_id=new_chat_completion_id(),
                model_id=requested_model,
                content=content,
                tool_calls=None,
                finish_reason="stop",
                usage=_build_usage_payload(
                    input_tokens=0,
                    output_tokens=0,
                    cost_origin="platform",
                ),
                system_fingerprint=None,
            )
        )

    resolved = _resolve_agent_llm_model(requested_model)
    llm = await _prepare_agent_llm_client(body=body, resolved=resolved)

    response_model_id = requested_model
    if body.stream:
        return StreamingResponse(
            _stream_agent_llm_sse(
                body=body,
                llm=llm,
                response_model_id=response_model_id,
            ),
            media_type="text/event-stream",
        )

    try:
        (
            content,
            tool_calls_json,
            input_tokens,
            output_tokens,
            _provider,
            _model,
            _source,
        ) = await _run_agent_llm_call(
            body=body,
            llm=llm,
        )
    except Exception as exc:
        logger.warning(
            "agent.llm_proxy.call_failed",
            requested_model=body.model,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        error_provider = _require_agent_error_provider(resolved.provider)
        status_code = 429 if _is_rate_limit_error(exc, provider=error_provider) else 502
        raise WsCommandError(
            "rate_limited" if status_code == 429 else "upstream",
            _agent_llm_error_message(exc, response_model_id, provider=error_provider),
            error_code="llm_proxy_rate_limited" if status_code == 429 else "llm_proxy_upstream",
        ) from exc
    finish_reason = "tool_calls" if tool_calls_json else "stop"
    return JSONResponse(
        build_chat_completion(
            completion_id=new_chat_completion_id(),
            model_id=response_model_id,
            content=content,
            tool_calls=tool_calls_json,
            finish_reason=finish_reason,
            usage=_build_usage_payload(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_origin=resolved.cost_origin,
            ),
            system_fingerprint=None,
        )
    )


async def dispatch_images_generations(
    *,
    body: AgentOpenAIImagesGenerationsRequest,
    shared_storage: SharedStorage,
) -> JSONResponse:
    _ = body.size
    model_id = body.model.strip() if body.model.strip() else IMAGE_AUTO_MODEL_ID
    if model_id != IMAGE_AUTO_MODEL_ID:
        raise WsCommandError(
            "ws_invalid_payload",
            f"images/generations supports only model={IMAGE_AUTO_MODEL_ID!r}",
            error_code="image_gen_model_invalid",
        )
    num_images = body.n if body.n is not None else 1
    if num_images < 1 or num_images > 4:
        raise WsCommandError(
            "ws_invalid_payload",
            "n must be in range 1..4",
            error_code="image_gen_n_invalid",
        )

    resolved = resolve_ai_model(AICapability.IMAGE_GEN, include_platform_default=True)
    if resolved is None:
        raise WsCommandError(
            "unavailable",
            "image_gen is unavailable for the company",
            error_code="image_gen_unavailable",
        )

    client = NanoBananaClient(storage=shared_storage)
    try:
        file_ids = await client.generate_images(prompt=body.prompt, num_images=num_images)
    except BillingBalanceBlockedError as exc:
        raise WsCommandError(
            "forbidden",
            str(exc),
            error_code="billing_balance_blocked",
        ) from exc
    except ValueError as exc:
        raise WsCommandError(
            "unavailable",
            str(exc),
            error_code="image_gen_unavailable",
        ) from exc
    if not file_ids:
        raise WsCommandError(
            "upstream",
            "image_gen returned no files",
            error_code="image_gen_empty",
        )

    response_format = body.response_format if body.response_format is not None else "b64_json"
    data_items: list[JsonObject] = []
    for file_id in file_ids:
        if response_format == "b64_json":
            data_items.append({"b64_json": await _file_id_to_b64_json(shared_storage, file_id)})
        else:
            data_items.append({"url": f"file:{file_id}"})
    return JSONResponse({"created": int(time.time()), "data": data_items})

