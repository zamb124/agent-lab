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
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import Response as StarletteResponse

from apps.flows.src.agent.llm_auth import LlmProxyAuthResult, require_llm_proxy_auth
from apps.flows.src.agent.llm_lara import (
    list_lara_branch_model_ids,
    load_lara_branch_ids,
    run_lara_chat_completion,
)
from apps.flows.src.dependencies import ContainerDep
from core.a2a import (
    coerce_usage_token_count,
    get_part_text,
    mapping_from_struct,
    part_has_text,
)
from core.ai.models import ResolvedAIModel
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
from core.ai.runtime import create_llm_client_from_ai_model, should_use_platform_default_free_pool
from core.billing import get_billing_service
from core.billing.exceptions import BillingBalanceBlockedError
from core.billing.service import BALANCE_BLOCK_OPERATION_LLM
from core.clients.llm.context_layer import openai_messages_to_a2a_messages
from core.clients.llm.messages import LLMToolCall
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
from core.config import get_settings
from core.context import get_context, require_context
from core.files.models import FileRecord
from core.files.s3_client import S3ClientFactory
from core.logging import get_logger
from core.office.ai_settings import (
    IMAGE_AUTO_MODEL_ID,
    LARA_MODEL_PREFIX,
    parse_lara_branch_model_id,
)
from core.tracing.tracer import get_tracer
from core.types import (
    JsonArray,
    JsonObject,
    JsonValue,
    parse_json_object,
    require_json_array,
    require_json_object,
)

logger = get_logger(__name__)
router = APIRouter(tags=["agent-llm-proxy"])

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


def install_llm_proxy_exception_handlers(app: FastAPI) -> None:
    """OpenAI/OR error envelope ``{"error":{message,type,code}}`` для LLM proxy surface."""
    app.add_exception_handler(HTTPException, _llm_proxy_http_exception_handler)


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
            raise HTTPException(
                status_code=503,
                detail="humanitec_llm недоступен для компании",
            )
        return resolved

    if requested_model == IMAGE_AUTO_MODEL_ID:
        raise HTTPException(
            status_code=400,
            detail="model 'image-auto' доступен только через /images/generations",
        )

    if parse_lara_branch_model_id(requested_model) is not None:
        raise HTTPException(
            status_code=400,
            detail="lara:<branch> обрабатывается отдельным A2A bridge",
        )

    parsed_ref = split_humanitec_llms_model_ref(requested_model)
    if parsed_ref is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "model должен быть 'auto', 'lara:<branch>', 'image-auto' "
                + "или '<provider>:<model_id>'"
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
    append_model_id(IMAGE_AUTO_MODEL_ID)

    lara_branches = await load_lara_branch_ids(container)
    for lara_model_id in list_lara_branch_model_ids(lara_branches):
        append_model_id(lara_model_id)

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

    if len(model_ids) == 2 + len(lara_branches):
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
    if normalized.startswith(LARA_MODEL_PREFIX) and parse_lara_branch_model_id(normalized) is None:
        raise HTTPException(status_code=400, detail="lara:<branch_id> требует непустой branch_id")
    if normalized not in allowed_model_ids:
        raise HTTPException(
            status_code=400,
            detail=f"model {normalized!r} недоступен для LLM proxy",
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
        raise ValueError("agent llm_proxy: provider обязателен для классификации ошибки")
    return provider


def _agent_error_provider(state: _AgentLlmCallState, resolved: ResolvedAIModel) -> str:
    runtime_provider = state.resolved_llm_provider
    if runtime_provider is not None and runtime_provider.strip():
        return runtime_provider
    return _require_agent_error_provider(resolved.provider)


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
    resolved: ResolvedAIModel,
    allow_platform_paid_fallback: bool,
) -> AsyncIterator[str | _AgentLlmCallState]:
    """
    Единый путь LLMClient.stream: yield content deltas, финальный yield — состояние вызова.

    Platform LLM context layer не включается (``llm_context=None``) — Goose/OO passthrough.
    """
    llm = create_llm_client_from_ai_model(
        resolved,
        max_tokens=body.max_tokens,
        temperature=body.temperature,
        allow_platform_paid_fallback=allow_platform_paid_fallback,
        top_p=body.top_p,
        frequency_penalty=body.frequency_penalty,
        presence_penalty=body.presence_penalty,
        seed=body.seed,
    )
    openai_messages = _agent_messages_to_openai_json(body.messages)
    a2a_messages = openai_messages_to_a2a_messages(openai_messages)
    tools_schema = _tools_schema(body.tools)
    extra_body = _stream_extra_body(body)

    tracer = get_tracer()
    llm_provider = llm.llm_provider
    llm_start = time.time()
    state = _AgentLlmCallState()

    async with tracer.llm_call_span(
        body.model,
        len(a2a_messages),
        len(tools_schema) if tools_schema else 0,
        llm_provider=llm_provider,
    ) as llm_span:
        tracer.record_llm_request(llm_span, openai_messages, tools_schema, None)

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

        tool_calls_json = state.tool_calls_json()
        llm_duration = (time.time() - llm_start) * 1000
        tracer.record_llm_response(
            llm_span,
            input_tokens=state.input_tokens,
            output_tokens=state.output_tokens,
            has_tool_calls=bool(tool_calls_json),
            duration_ms=llm_duration,
            response_content=state.content,
            tool_calls=tool_calls_json,
            llm_provider=state.resolved_llm_provider or llm_provider,
            llm_model=state.resolved_llm_model,
            candidate_source=state.resolved_llm_source,
            cost_origin=resolved.cost_origin,
        )

    yield state


async def _run_agent_llm_call(
    *,
    body: AgentOpenAIChatCompletionsRequest,
    resolved: ResolvedAIModel,
    allow_platform_paid_fallback: bool,
) -> tuple[str, list[JsonObject] | None, int, int, str | None, str | None, str | None]:
    state: _AgentLlmCallState | None = None
    async for item in _iter_agent_llm_content_deltas(
        body=body,
        resolved=resolved,
        allow_platform_paid_fallback=allow_platform_paid_fallback,
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
    resolved: ResolvedAIModel,
    allow_platform_paid_fallback: bool,
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
        resolved=resolved,
        allow_platform_paid_fallback=allow_platform_paid_fallback,
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
                        provider=_agent_error_provider(state, resolved),
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
                cost_origin=resolved.cost_origin,
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


async def _file_id_to_b64_json(container: ContainerDep, file_id: str) -> str:
    file_payload = await container.shared_storage.get(f"file:{file_id}")
    if file_payload is None:
        raise HTTPException(status_code=502, detail=f"сгенерированный файл {file_id} не найден")
    file_record = FileRecord.model_validate_json(file_payload)
    s3_client = S3ClientFactory.create_client_for_bucket(file_record.s3_bucket)
    try:
        file_bytes = await s3_client.download_bytes(file_record.s3_key)
    finally:
        await s3_client.close()
    if not file_bytes:
        raise HTTPException(status_code=502, detail=f"пустой файл {file_id}")
    return base64.b64encode(file_bytes).decode("ascii")


def _proxy_target_path(target: str) -> str:
    parsed = urlparse(target.strip())
    path = parsed.path if parsed.scheme else target.strip()
    if not path.startswith("/"):
        path = f"/{path}"
    marker = "/agent/llm/v1/"
    idx = path.find(marker)
    if idx < 0:
        raise HTTPException(
            status_code=400,
            detail="proxy target должен указывать на /flows/api/v1/agent/llm/v1/…",
        )
    return path[idx + len(marker) :].strip("/")


def _validate_chat_request_n(body: AgentOpenAIChatCompletionsRequest) -> None:
    if body.n is None or body.n == 1:
        return
    raise HTTPException(status_code=400, detail="n > 1 не поддерживается LLM proxy")


async def _dispatch_chat_completions(
    *,
    body: AgentOpenAIChatCompletionsRequest,
    container: ContainerDep,
    auth: LlmProxyAuthResult,
) -> JSONResponse | StreamingResponse:
    if not body.messages:
        raise HTTPException(status_code=400, detail="messages обязателен")
    _validate_chat_request_n(body)

    model_ids = await _read_agent_llm_model_ids(container)
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
        content = await run_lara_chat_completion(
            container,
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
    try:
        allow_platform_paid_fallback = await _prepare_agent_llm_billing(resolved=resolved)
    except BillingBalanceBlockedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    response_model_id = requested_model
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
            resolved=resolved,
            allow_platform_paid_fallback=allow_platform_paid_fallback,
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
        raise HTTPException(
            status_code=status_code,
            detail=_agent_llm_error_message(exc, response_model_id, provider=error_provider),
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


async def _dispatch_images_generations(
    *,
    body: AgentOpenAIImagesGenerationsRequest,
    container: ContainerDep,
) -> JSONResponse:
    _ = body.size
    model_id = body.model.strip() if body.model.strip() else IMAGE_AUTO_MODEL_ID
    if model_id != IMAGE_AUTO_MODEL_ID:
        raise HTTPException(
            status_code=400,
            detail=f"images/generations поддерживает только model={IMAGE_AUTO_MODEL_ID!r}",
        )
    num_images = body.n if body.n is not None else 1
    if num_images < 1 or num_images > 4:
        raise HTTPException(status_code=400, detail="n должен быть в диапазоне 1..4")

    resolved = resolve_ai_model(AICapability.IMAGE_GEN, include_platform_default=True)
    if resolved is None:
        raise HTTPException(status_code=503, detail="image_gen недоступен для компании")

    client = NanoBananaClient(storage=container.shared_storage)
    try:
        file_ids = await client.generate_images(prompt=body.prompt, num_images=num_images)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not file_ids:
        raise HTTPException(status_code=502, detail="image_gen не вернул файлы")

    response_format = body.response_format if body.response_format is not None else "b64_json"
    data_items: list[JsonObject] = []
    for file_id in file_ids:
        if response_format == "b64_json":
            data_items.append({"b64_json": await _file_id_to_b64_json(container, file_id)})
        else:
            data_items.append({"url": f"file:{file_id}"})
    return JSONResponse({"created": int(time.time()), "data": data_items})


@router.get("/agent/llm/v1/models", tags=["agent-llm-proxy", "public"])
async def agent_llm_models(
    request: Request,
    container: ContainerDep,
) -> AgentOpenAIModelsResponse:
    _ = await require_llm_proxy_auth(request, container)
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
    auth = await require_llm_proxy_auth(request, container)
    _ = require_context()
    return await _dispatch_chat_completions(body=body, container=container, auth=auth)


@router.post(
    "/agent/llm/v1/images/generations",
    tags=["agent-llm-proxy", "public"],
    response_model=None,
)
async def agent_llm_images_generations(
    body: AgentOpenAIImagesGenerationsRequest,
    request: Request,
    container: ContainerDep,
) -> JSONResponse:
    _ = await require_llm_proxy_auth(request, container)
    _ = require_context()
    return await _dispatch_images_generations(body=body, container=container)


@router.post(
    "/agent/llm/v1/proxy",
    tags=["agent-llm-proxy", "public"],
    response_model=None,
)
async def agent_llm_onlyoffice_proxy(
    envelope: OnlyOfficeLlmProxyEnvelope,
    request: Request,
    container: ContainerDep,
) -> JSONResponse | StreamingResponse | Response:
    """Unwrap OnlyOffice AI ``{target,method,headers,data}`` → OpenAI handlers."""
    auth = await require_llm_proxy_auth(request, container)
    _ = require_context()
    method = envelope.method.strip().upper()
    if method not in {"GET", "POST"}:
        raise HTTPException(status_code=400, detail=f"proxy method {method!r} не поддерживается")

    relative = _proxy_target_path(envelope.target)
    logger.info(
        "agent.llm_proxy.onlyoffice_proxy",
        target_path=relative,
        method=method,
        auth_kind=auth.kind,
    )

    if relative == "models":
        if method != "GET":
            raise HTTPException(status_code=405, detail="models только GET")
        model_ids = await _read_agent_llm_model_ids(container)
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
                raise HTTPException(
                    status_code=400,
                    detail="proxy.data должен быть JSON object",
                ) from exc
    elif isinstance(raw_data, dict):
        payload = require_json_object(raw_data, "onlyoffice.proxy.data")
    elif raw_data is None:
        payload = {}
    else:
        raise HTTPException(status_code=400, detail="proxy.data должен быть JSON object или string")

    if relative == "chat/completions":
        if method != "POST":
            raise HTTPException(status_code=405, detail="chat/completions только POST")
        body = AgentOpenAIChatCompletionsRequest.model_validate(payload)
        return await _dispatch_chat_completions(body=body, container=container, auth=auth)

    if relative == "images/generations":
        if method != "POST":
            raise HTTPException(status_code=405, detail="images/generations только POST")
        images_body = AgentOpenAIImagesGenerationsRequest.model_validate(payload)
        return await _dispatch_images_generations(body=images_body, container=container)

    raise HTTPException(status_code=404, detail=f"proxy target path {relative!r} не найден")
