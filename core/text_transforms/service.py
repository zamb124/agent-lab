"""Сервис суммаризации и форматирования текста через платформенные LLM capabilities."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from a2a.helpers.proto_helpers import get_message_text
from a2a.types import Message, Part, Role
from opentelemetry import trace as otel_trace
from tenacity import RetryCallState, retry, retry_if_exception_type, stop_after_attempt

from core.a2a.codec import mapping_from_struct
from core.ai.llm_config import ReasoningEffort
from core.ai.models import ResolvedAIModel
from core.ai.provider_error import AI_PROVIDER_IO_ERRORS
from core.ai.providers import AICapability, split_provider_prefixed_model
from core.ai.requirements import AISelection
from core.ai.resolver import resolve_ai_model
from core.ai.runtime import (
    create_llm_client_from_ai_model,
    create_vision_llm_client,
    resolve_vision_ai_model,
)
from core.billing.service import BillingService
from core.clients.llm.client import LLMClient
from core.clients.llm.messages import build_a2a_message
from core.clients.llm.mock import MockLLM
from core.config import get_settings
from core.logging import get_logger
from core.text_transforms.chunking import split_text_into_markdown_chunks
from core.tracing import attributes as tattr
from core.tracing.operation_span import traced_operation
from core.types import (
    JsonObject,
    JsonValue,
    parse_json_value,
    require_json_array,
    require_json_object,
)

_MARKDOWN_TO_MD_SYSTEM = (
    "You convert plain text into clean, structured Markdown. "
    "Output ONLY the Markdown for this part. No preamble, no explanation, no code fences around the whole answer. "
    "Preserve the source language. Use headings, lists, and emphasis where they improve readability."
)

_DEFAULT_SUMMARY_INSTRUCTION = (
    "Summarize the following text clearly and concisely. Preserve the original language. "
    "Output only the summary, no preamble."
)
_INTERNAL_TEXT_TRANSFORM_LLM_CONTEXT: JsonObject = {"profile": "off", "budget": "max"}
_SUMMARIZATION_REASONING_EFFORT: ReasoningEffort = "none"
_SUMMARIZE_FIRST_TOKEN_TIMEOUT_SECONDS: float = 30.0
_SUMMARIZE_ATTEMPT_TIMEOUT_SECONDS: float = 180.0
_SUMMARIZE_MAX_ATTEMPTS: int = 3

logger = get_logger(__name__)


def _log_summarize_retry(retry_state: RetryCallState) -> None:
    exc = retry_state.outcome.exception() if retry_state.outcome is not None else None
    span = otel_trace.get_current_span()
    if span.is_recording():
        span.set_attribute(tattr.ATTR_LLM_ATTEMPTS, retry_state.attempt_number + 1)
        if exc is not None:
            span.set_attribute(tattr.ATTR_LLM_ATTEMPT_ERROR, type(exc).__name__)
    logger.warning(
        "text_transforms.summarize_attempt_failed",
        attempt=retry_state.attempt_number,
        max_attempts=_SUMMARIZE_MAX_ATTEMPTS,
        error=str(exc),
        error_type=type(exc).__name__ if exc is not None else "unknown",
    )


# Ретраи LLM-суммаризации: провайдерские флаки (таймаут первого токена,
# обрыв/столл стрима, HTTP-ошибка, ответ без tool_calls или с пустым текстом) —
# транзиентны; детерминированные ошибки валидации сюда не попадают.
_summarize_retry = retry(
    retry=retry_if_exception_type(AI_PROVIDER_IO_ERRORS),
    stop=stop_after_attempt(_SUMMARIZE_MAX_ATTEMPTS),
    before_sleep=_log_summarize_retry,
    reraise=True,
)


def _summarize_first_token_bound(llm: LLMClient | MockLLM) -> None:
    if isinstance(llm, LLMClient):
        llm.first_token_timeout = _SUMMARIZE_FIRST_TOKEN_TIMEOUT_SECONDS

SUBMIT_PAGE_SUMMARY_TOOL_NAME: str = "submit_page_summary"

_STRUCTURED_SUMMARY_INSTRUCTION = (
    "Extract structured data from the document page below. "
    f"Call the tool {SUBMIT_PAGE_SUMMARY_TOOL_NAME} exactly once with arguments that match "
    "the tool JSON Schema. Use both the page text and any attached images. "
    "Do not write prose outside the tool call."
)


class TextTransformService:
    """
    Суммаризация резолвит company capability override и поддерживает явные
    provider/model аргументы только если override не задан.

    Текст — ``AICapability.LLM_SUMMARIZE``; при ``media_parts`` (картинки) —
    ``AICapability.LLM_VISION``, чтобы модель видела Part(raw).

    Форматирование Markdown всегда идёт через ``AICapability.LLM_FORMAT_MARKDOWN``.
    LitServe не является LLM-провайдером для markdown.
    """

    def __init__(self, billing_service: BillingService) -> None:
        self.billing_service: BillingService = billing_service

    async def summarize(
        self,
        text: str,
        *,
        max_output_tokens: int | None = None,
        instruction: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        media_parts: Sequence[Part] | None = None,
    ) -> str:
        async with traced_operation(
            "core.text_transforms.summarize",
            operation_category="llm",
            extra_attributes={
                tattr.ATTR_FILES_CHARS: len(text),
                tattr.ATTR_FILES_HAS_IMAGES: bool(media_parts),
            },
        ):
            return await self._summarize_inner(
                text,
                max_output_tokens=max_output_tokens,
                instruction=instruction,
                provider=provider,
                model=model,
                media_parts=media_parts,
            )

    async def _summarize_inner(
        self,
        text: str,
        *,
        max_output_tokens: int | None,
        instruction: str | None,
        provider: str | None,
        model: str | None,
        media_parts: Sequence[Part] | None,
    ) -> str:
        stripped = text.strip()
        media = list(media_parts) if media_parts is not None else []
        if not stripped and not media:
            raise ValueError('summarize: text is empty')

        sys_text = (
            instruction.strip()
            if instruction is not None and instruction.strip()
            else _DEFAULT_SUMMARY_INSTRUCTION
        )
        lead = sys_text if not stripped else f"{sys_text}\n\n{stripped}"
        parts: list[Part] = [Part(text=lead), *media]
        messages: list[Message] = [
            build_a2a_message(
                role=Role.ROLE_USER,
                parts=parts,
            ),
        ]
        if media:
            # Картинки — тот же vision-маршрут, что OCR страниц (в тестах → MockLLM).
            if provider is not None and model is not None:
                vision_model = f"{provider}:{model}"
            elif model is not None:
                vision_model = model
            else:
                vision_model = None
            llm = create_vision_llm_client(
                resolve_vision_ai_model(vision_model),
                billing_service=self.billing_service,
            )
        else:
            resolved = self._resolve_company_llm_args(
                AICapability.LLM_SUMMARIZE,
                provider=provider,
                model=model,
            )
            llm = create_llm_client_from_ai_model(
                resolved,
                billing_service=self.billing_service,
                max_tokens=max_output_tokens,
            )
        _summarize_first_token_bound(llm)

        @_summarize_retry
        async def _once() -> str:
            async with asyncio.timeout(_SUMMARIZE_ATTEMPT_TIMEOUT_SECONDS):
                out = await llm.chat(
                    messages,
                    llm_context=_INTERNAL_TEXT_TRANSFORM_LLM_CONTEXT,
                    reasoning_effort=_SUMMARIZATION_REASONING_EFFORT,
                )
            summary = get_message_text(out).strip()
            if not summary:
                raise ValueError('summarize: empty model response')
            return summary

        return await _once()

    async def summarize_structured(
        self,
        text: str,
        *,
        schema: JsonObject,
        instruction: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        media_parts: Sequence[Part] | None = None,
    ) -> JsonObject:
        """Суммаризация через forced tool_choice ``submit_page_summary`` + JSON Schema.

        ``schema`` — JSON Schema object root параметров tool. Ответ — arguments tool call.
        """
        async with traced_operation(
            "core.text_transforms.summarize_structured",
            operation_category="llm",
            extra_attributes={
                tattr.ATTR_FILES_CHARS: len(text),
                tattr.ATTR_FILES_HAS_IMAGES: bool(media_parts),
            },
        ):
            return await self._summarize_structured_inner(
                text,
                schema=schema,
                instruction=instruction,
                provider=provider,
                model=model,
                media_parts=media_parts,
            )

    async def _summarize_structured_inner(
        self,
        text: str,
        *,
        schema: JsonObject,
        instruction: str | None,
        provider: str | None,
        model: str | None,
        media_parts: Sequence[Part] | None,
    ) -> JsonObject:
        schema_type = schema.get("type")
        if schema_type != "object":
            raise ValueError("summarize_structured: schema.type must be 'object'")
        stripped = text.strip()
        media = list(media_parts) if media_parts is not None else []
        if not stripped and not media:
            raise ValueError("summarize_structured: text is empty")

        focus = instruction.strip() if instruction is not None and instruction.strip() else ""
        sys_text = _STRUCTURED_SUMMARY_INSTRUCTION
        if focus:
            sys_text = f"{sys_text}\nAdditional focus: {focus}"
        lead = sys_text if not stripped else f"{sys_text}\n\n{stripped}"
        parts: list[Part] = [Part(text=lead), *media]
        messages: list[Message] = [
            build_a2a_message(
                role=Role.ROLE_USER,
                parts=parts,
            ),
        ]
        tools: list[JsonObject] = [
            {
                "type": "function",
                "function": {
                    "name": SUBMIT_PAGE_SUMMARY_TOOL_NAME,
                    "description": (
                        "Submit the structured summary for the current document page. "
                        "Call exactly once."
                    ),
                    "parameters": schema,
                },
            }
        ]
        extra_body: JsonObject = {
            "tool_choice": {
                "type": "function",
                "function": {"name": SUBMIT_PAGE_SUMMARY_TOOL_NAME},
            }
        }
        if media:
            if provider is not None and model is not None:
                vision_model = f"{provider}:{model}"
            elif model is not None:
                vision_model = model
            else:
                vision_model = None
            llm = create_vision_llm_client(
                resolve_vision_ai_model(vision_model),
                billing_service=self.billing_service,
            )
        else:
            resolved = self._resolve_company_llm_args(
                AICapability.LLM_SUMMARIZE,
                provider=provider,
                model=model,
            )
            llm = create_llm_client_from_ai_model(
                resolved,
                billing_service=self.billing_service,
            )
        _summarize_first_token_bound(llm)

        @_summarize_retry
        async def _once() -> JsonObject:
            async with asyncio.timeout(_SUMMARIZE_ATTEMPT_TIMEOUT_SECONDS):
                out = await llm.chat(
                    messages,
                    tools=tools,
                    extra_body=extra_body,
                    llm_context=_INTERNAL_TEXT_TRANSFORM_LLM_CONTEXT,
                    reasoning_effort=_SUMMARIZATION_REASONING_EFFORT,
                )
            return _submit_page_summary_arguments(out)

        return await _once()

    async def format_markdown(
        self,
        text: str,
    ) -> str:
        async with traced_operation(
            "core.text_transforms.format_markdown",
            operation_category="llm",
            extra_attributes={tattr.ATTR_FILES_CHARS: len(text)},
        ):
            return await self._format_markdown_inner(text)

    async def _format_markdown_inner(self, text: str) -> str:
        stripped = text.strip()
        if not stripped:
            raise ValueError('format_markdown: text is empty')

        resolved = self._resolve_company_llm_args(
            AICapability.LLM_FORMAT_MARKDOWN,
            provider=None,
            model=None,
        )
        settings = get_settings()
        text_transform_cfg = settings.text_transforms
        chunk_lim = int(text_transform_cfg.markdown_max_chunk_chars)

        llm = create_llm_client_from_ai_model(
            resolved, billing_service=self.billing_service
        )
        chunks = split_text_into_markdown_chunks(stripped, int(chunk_lim))
        if not chunks:
            raise ValueError('format_markdown: no chunks after split')

        joiner = text_transform_cfg.markdown_chunk_join
        formatted_parts: list[str] = []
        total = len(chunks)
        for i, chunk in enumerate(chunks):
            user_prompt = (
                f"This is part {i + 1} of {total}. Convert only the following text to Markdown:\n\n{chunk}"
            )
            msg = build_a2a_message(
                role=Role.ROLE_USER,
                parts=[
                    Part(text=_MARKDOWN_TO_MD_SYSTEM + "\n\n" + user_prompt),
                ],
            )
            out = await llm.chat([msg], llm_context=_INTERNAL_TEXT_TRANSFORM_LLM_CONTEXT)
            piece = get_message_text(out).strip()
            formatted_parts.append(piece)

        result = joiner.join(formatted_parts).strip()
        if not result:
            raise ValueError('format_markdown: empty LLM-path result')
        return result

    def _resolve_company_llm_args(
        self,
        capability: AICapability,
        *,
        provider: str | None,
        model: str | None,
    ) -> ResolvedAIModel:
        rp, rm = split_provider_prefixed_model(provider, model)
        resolved = resolve_ai_model(capability, include_platform_default=False)
        if resolved is not None:
            return resolved
        if rp is None and rm is None:
            resolved = resolve_ai_model(capability, include_platform_default=True)
            if resolved is None:
                raise ValueError(
                    f"TextTransformService: platform default for capability={capability.value} "
                    + 'is not configured'
                )
            return resolved
        if rp is None:
            raise ValueError(
                f"TextTransformService: for capability={capability.value} provider and model "
                + 'must be set together'
            )
        resolved = resolve_ai_model(
            capability,
            selection=AISelection(provider=rp, model=rm),
            include_platform_default=False,
        )
        if resolved is None:
            raise ValueError(
                f"TextTransformService: explicit provider/model for capability={capability.value} "
                + 'failed to resolve'
            )
        return resolved


def _submit_page_summary_arguments(message: Message) -> JsonObject:
    if not message.HasField("metadata"):
        raise ValueError(
            f"summarize_structured: model did not call {SUBMIT_PAGE_SUMMARY_TOOL_NAME}"
        )
    metadata = mapping_from_struct(message.metadata)
    raw_tool_calls = metadata.get("tool_calls")
    if raw_tool_calls is None:
        raise ValueError(
            f"summarize_structured: model did not call {SUBMIT_PAGE_SUMMARY_TOOL_NAME}"
        )
    tool_calls = require_json_array(
        raw_tool_calls,
        "summarize_structured.tool_calls",
    )
    matching: JsonObject | None = None
    for index, raw_call in enumerate(tool_calls):
        call = require_json_object(raw_call, f"summarize_structured.tool_calls[{index}]")
        name = _tool_call_name(call, f"summarize_structured.tool_calls[{index}]")
        if name != SUBMIT_PAGE_SUMMARY_TOOL_NAME:
            continue
        arguments = _tool_call_arguments(call, f"summarize_structured.tool_calls[{index}]")
        if matching is not None:
            raise ValueError(
                f"summarize_structured: {SUBMIT_PAGE_SUMMARY_TOOL_NAME} called more than once"
            )
        matching = arguments
    if matching is None:
        raise ValueError(
            f"summarize_structured: model did not call {SUBMIT_PAGE_SUMMARY_TOOL_NAME}"
        )
    return matching


def _tool_call_name(call: JsonObject, field_name: str) -> str:
    top_level = call.get("name")
    if isinstance(top_level, str) and top_level.strip():
        return top_level.strip()
    function = call.get("function")
    if isinstance(function, dict):
        nested_name = function.get("name")
        if isinstance(nested_name, str) and nested_name.strip():
            return nested_name.strip()
    raise ValueError(f"{field_name}: tool name is required")


def _tool_call_arguments(call: JsonObject, field_name: str) -> JsonObject:
    top_level = _coerce_tool_arguments(call.get("arguments"), f"{field_name}.arguments")
    function = call.get("function")
    nested: JsonObject | None = None
    if isinstance(function, dict):
        nested = _coerce_tool_arguments(
            function.get("arguments"),
            f"{field_name}.function.arguments",
        )
    if top_level is not None and nested is not None and top_level != nested:
        raise ValueError(f"{field_name}: conflicting tool arguments")
    if top_level is not None:
        return top_level
    if nested is not None:
        return nested
    raise ValueError(f"{field_name}: tool arguments are required")


def _coerce_tool_arguments(raw: JsonValue, field_name: str) -> JsonObject | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return require_json_object(raw, field_name)
    if isinstance(raw, str):
        stripped = raw.strip()
        if stripped == "":
            raise ValueError(f"{field_name}: empty arguments string")
        return require_json_object(parse_json_value(stripped, field_name), field_name)
    raise ValueError(f"{field_name}: expected object or JSON string")
