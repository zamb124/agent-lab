"""Сервис суммаризации и форматирования текста в Markdown (LLM и HTTP LitServe)."""

from __future__ import annotations

import uuid
from typing import Any

from a2a.types import Message, Part, Role, TextPart
from a2a.utils.message import get_message_text

from core.billing import get_billing_service
from core.billing.service import BALANCE_BLOCK_OPERATION_LLM
from core.clients.llm.factory import get_llm
from core.clients.llm.model_routing import split_provider_prefixed_model
from core.clients.service_client import ServiceClient, ServiceClientError
from core.config import get_settings
from core.context import get_context
from core.models.billing_models import UsageType
from core.rag.openai_http_contracts import PROVIDER_LITSERVE_PLACEHOLDER_BEARER
from core.text_transforms.chunking import split_text_into_markdown_chunks
from core.text_transforms.format_markdown_response import validate_format_markdown_response
from core.text_transforms.routing import should_use_litserve_format_markdown_http
from core.tracing import attributes as trace_attributes
from core.tracing.operation_span import traced_operation

_MARKDOWN_TO_MD_SYSTEM = (
    "You convert plain text into clean, structured Markdown. "
    "Output ONLY the Markdown for this part. No preamble, no explanation, no code fences around the whole answer. "
    "Preserve the source language. Use headings, lists, and emphasis where they improve readability."
)

_DEFAULT_SUMMARY_INSTRUCTION = (
    "Summarize the following text clearly and concisely. Preserve the original language. "
    "Output only the summary, no preamble."
)


class TextTransformService:
    """
    Суммаризация через ``get_llm`` (включая ``provider_litserve`` как OpenAI-compatible chat).

    Форматирование в Markdown:
    - по умолчанию — ``get_llm()`` с платформенной candidate/fallback стратегией;
    - при явном ``provider_litserve`` — ``POST /v1/text/format_markdown`` (LitServe);
    - при явном ``openrouter`` / ``openai`` / ``bothub`` / ``yandex`` — чанкованный вызов ``get_llm``.

    Префикс в поле model: ``openrouter:vendor/model`` разбирается в ``(openrouter, vendor/model)``.
    Если ``provider`` и ``model`` не заданы, суммаризация и Markdown используют платформенный
    default-route ``get_llm()``. Явный ``provider_litserve`` сохраняет старый HTTP-путь Markdown.
    """

    async def summarize(
        self,
        text: str,
        *,
        max_output_tokens: int | None = None,
        instruction: str | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> str:
        stripped = text.strip()
        if not stripped:
            raise ValueError("summarize: text пуст")

        await self._require_llm_balance()
        rp, rm = split_provider_prefixed_model(provider, model)
        llm = get_llm(
            model_name=rm,
            provider=rp,
            max_tokens=max_output_tokens,
        )
        sys_text = instruction.strip() if instruction is not None and instruction.strip() else _DEFAULT_SUMMARY_INSTRUCTION
        messages: list[Message] = [
            Message(
                messageId=str(uuid.uuid4()),
                role=Role.user,
                parts=[Part(root=TextPart(text=sys_text + "\n\n" + stripped))],
            ),
        ]
        out = await llm.chat(messages)
        if not isinstance(out, Message):
            raise TypeError("summarize: ожидан Message от LLM")
        summary = get_message_text(out).strip()
        if not summary:
            raise ValueError("summarize: пустой ответ модели")
        return summary

    async def format_markdown(
        self,
        text: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        max_chunk_chars: int | None = None,
    ) -> str:
        stripped = text.strip()
        if not stripped:
            raise ValueError("format_markdown: text пуст")

        rp, rm = split_provider_prefixed_model(provider, model)
        settings = get_settings()
        infra = settings.provider_litserve.infra
        chunk_lim = max_chunk_chars if max_chunk_chars is not None else infra.markdown_max_chunk_chars

        if should_use_litserve_format_markdown_http(rp):
            model_for_litserve = rm if rm is not None and str(rm).strip() else infra.markdown_default_api_model_id
            if not str(model_for_litserve).strip():
                raise ValueError("format_markdown: пустой model для LitServe")
            return await self._format_markdown_litserve_http(
                stripped,
                model_id=str(model_for_litserve).strip(),
                max_chunk_chars=int(chunk_lim),
            )

        await self._require_llm_balance()
        llm = get_llm(
            provider=rp,
            model_name=str(rm).strip() if rm is not None and str(rm).strip() else None,
        )
        chunks = split_text_into_markdown_chunks(stripped, int(chunk_lim))
        if not chunks:
            raise ValueError("format_markdown: нет чанков после разбиения")

        joiner = infra.markdown_chunk_join
        formatted_parts: list[str] = []
        total = len(chunks)
        for i, chunk in enumerate(chunks):
            user_prompt = (
                f"This is part {i + 1} of {total}. Convert only the following text to Markdown:\n\n{chunk}"
            )
            msg = Message(
                messageId=str(uuid.uuid4()),
                role=Role.user,
                parts=[
                    Part(root=TextPart(text=_MARKDOWN_TO_MD_SYSTEM + "\n\n" + user_prompt)),
                ],
            )
            out = await llm.chat([msg])
            if not isinstance(out, Message):
                raise TypeError("format_markdown: ожидан Message от LLM")
            piece = get_message_text(out).strip()
            formatted_parts.append(piece)

        result = joiner.join(formatted_parts).strip()
        if not result:
            raise ValueError("format_markdown: пустой результат LLM-пути")
        return result

    async def _require_llm_balance(self) -> None:
        actx = get_context()
        if actx is None or actx.active_company is None:
            raise ValueError("TextTransformService: нужен Context с active_company (биллинг)")
        if actx.user is None or not str(actx.user.user_id).strip():
            raise ValueError("TextTransformService: нужен Context с user (биллинг)")
        await get_billing_service().require_balance_for_billable_operation(
            actx.active_company.company_id,
            str(actx.user.user_id).strip(),
            operation_code=BALANCE_BLOCK_OPERATION_LLM,
            notification_service="flows",
        )

    async def _format_markdown_litserve_http(
        self,
        text: str,
        *,
        model_id: str,
        max_chunk_chars: int,
    ) -> str:
        await self._require_llm_balance()
        settings = get_settings()
        timeout = float(settings.provider_litserve.infra.request_timeout_seconds)
        client = ServiceClient()
        payload: dict[str, Any] = {
            "text": text,
            "model": model_id,
            "max_chunk_chars": max_chunk_chars,
        }
        async with traced_operation(
            "llm.provider_litserve.format_markdown",
            event_type="provider_litserve.format_markdown",
            operation_category="llm",
            billing_usage_type=UsageType.LLM_REQUEST.value,
            billing_resource_name=f"llm:{model_id}",
            billing_pending_settlement=True,
        ) as span:
            raw = await client.post(
                "provider_litserve",
                "/v1/text/format_markdown",
                json=payload,
                timeout=timeout,
                headers={"Authorization": f"Bearer {PROVIDER_LITSERVE_PLACEHOLDER_BEARER}"},
            )
            if not isinstance(raw, dict):
                raise ServiceClientError("provider_litserve format_markdown: ответ не JSON-object")
            validated = validate_format_markdown_response(raw)
            usage = validated.usage
            span.set_attribute(trace_attributes.ATTR_LLM_PROVIDER, "provider_litserve")
            span.set_attribute(trace_attributes.ATTR_LLM_MODEL, validated.model)
            span.set_attribute(trace_attributes.ATTR_LLM_INPUT_TOKENS, usage.prompt_tokens)
            span.set_attribute(trace_attributes.ATTR_LLM_OUTPUT_TOKENS, usage.completion_tokens)
            span.set_attribute(trace_attributes.ATTR_LLM_TOTAL_TOKENS, usage.total_tokens)
            span.set_attribute(
                trace_attributes.ATTR_BILLING_RESOURCE_NAME,
                f"llm:{validated.model}",
            )
            out_md = validated.markdown.strip()
            if not out_md:
                raise ValueError("format_markdown: пустой markdown в ответе LitServe")
            return out_md
