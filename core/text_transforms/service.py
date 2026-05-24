"""Сервис суммаризации и форматирования текста через платформенные LLM capabilities."""

from __future__ import annotations

import uuid

from a2a.types import Message, Part, Role, TextPart
from a2a.utils.message import get_message_text

from core.billing import get_billing_service
from core.billing.service import BALANCE_BLOCK_OPERATION_LLM
from core.clients.llm.config import LLMCallConfig
from core.clients.llm.factory import get_llm, should_use_platform_default_free_pool
from core.clients.llm.model_routing import split_provider_prefixed_model
from core.company_ai import (
    COST_ORIGIN_PLATFORM,
    CUSTOM_PROVIDER_REF_PREFIX,
    AICapability,
    resolve_custom_llm_provider_ref,
    resolve_llm_for_capability,
)
from core.config import get_settings
from core.context import get_context
from core.text_transforms.chunking import split_text_into_markdown_chunks
from core.types import JsonObject

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


class TextTransformService:
    """
    Суммаризация резолвит company capability override и поддерживает явные
    provider/model аргументы только если override не задан.

    Форматирование Markdown всегда идёт через ``AICapability.LLM_FORMAT_MARKDOWN``
    и общий ``get_llm()``. LitServe не является LLM-провайдером для markdown.
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

        (
            rp,
            rm,
            api_key,
            base_url,
            headers,
            body,
            fallback_models,
            cost_origin,
        ) = self._resolve_company_llm_args(
            AICapability.LLM_SUMMARIZE,
            provider=provider,
            model=model,
        )
        allow_platform_paid_fallback = await self._prepare_llm_billing(
            cost_origin=cost_origin,
            model=rm,
            provider=rp,
            api_key=api_key,
            base_url=base_url,
        )
        llm = get_llm(
            model_name=rm,
            provider=rp,
            max_tokens=max_output_tokens,
            api_key=api_key,
            base_url=base_url,
            extra_request_headers=headers,
            extra_request_body=body,
            fallback_models=fallback_models,
            allow_platform_paid_fallback=allow_platform_paid_fallback,
        )
        sys_text = instruction.strip() if instruction is not None and instruction.strip() else _DEFAULT_SUMMARY_INSTRUCTION
        messages: list[Message] = [
            Message(
                message_id=str(uuid.uuid4()),
                role=Role.user,
                parts=[Part(root=TextPart(text=sys_text + "\n\n" + stripped))],
            ),
        ]
        out = await llm.chat(messages, llm_context=_INTERNAL_TEXT_TRANSFORM_LLM_CONTEXT)
        summary = get_message_text(out).strip()
        if not summary:
            raise ValueError("summarize: пустой ответ модели")
        return summary

    async def format_markdown(
        self,
        text: str,
    ) -> str:
        stripped = text.strip()
        if not stripped:
            raise ValueError("format_markdown: text пуст")

        (
            rp,
            rm,
            api_key,
            base_url,
            headers,
            body,
            fallback_models,
            cost_origin,
        ) = self._resolve_company_llm_args(
            AICapability.LLM_FORMAT_MARKDOWN,
            provider=None,
            model=None,
        )
        settings = get_settings()
        text_transform_cfg = settings.text_transforms
        chunk_lim = int(text_transform_cfg.markdown_max_chunk_chars)

        allow_platform_paid_fallback = await self._prepare_llm_billing(
            cost_origin=cost_origin,
            model=rm,
            provider=rp,
            api_key=api_key,
            base_url=base_url,
        )
        llm = get_llm(
            provider=rp,
            model_name=str(rm).strip() if rm is not None and str(rm).strip() else None,
            api_key=api_key,
            base_url=base_url,
            extra_request_headers=headers,
            extra_request_body=body,
            fallback_models=fallback_models,
            allow_platform_paid_fallback=allow_platform_paid_fallback,
        )
        chunks = split_text_into_markdown_chunks(stripped, int(chunk_lim))
        if not chunks:
            raise ValueError("format_markdown: нет чанков после разбиения")

        joiner = text_transform_cfg.markdown_chunk_join
        formatted_parts: list[str] = []
        total = len(chunks)
        for i, chunk in enumerate(chunks):
            user_prompt = (
                f"This is part {i + 1} of {total}. Convert only the following text to Markdown:\n\n{chunk}"
            )
            msg = Message(
                message_id=str(uuid.uuid4()),
                role=Role.user,
                parts=[
                    Part(root=TextPart(text=_MARKDOWN_TO_MD_SYSTEM + "\n\n" + user_prompt)),
                ],
            )
            out = await llm.chat([msg], llm_context=_INTERNAL_TEXT_TRANSFORM_LLM_CONTEXT)
            piece = get_message_text(out).strip()
            formatted_parts.append(piece)

        result = joiner.join(formatted_parts).strip()
        if not result:
            raise ValueError("format_markdown: пустой результат LLM-пути")
        return result

    def _resolve_company_llm_args(
        self,
        capability: AICapability,
        *,
        provider: str | None,
        model: str | None,
    ) -> tuple[
        str | None,
        str | None,
        str | None,
        str | None,
        dict[str, str] | None,
        JsonObject | None,
        list[LLMCallConfig] | None,
        str,
    ]:
        rp, rm = split_provider_prefixed_model(provider, model)
        resolved = resolve_llm_for_capability(capability)
        if resolved is not None:
            return (
                resolved.provider,
                resolved.model,
                resolved.api_key,
                resolved.base_url,
                resolved.extra_request_headers,
                resolved.extra_request_body,
                list(resolved.fallback_models or ()) or None,
                resolved.cost_origin,
            )
        if rp and rp.startswith(CUSTOM_PROVIDER_REF_PREFIX):
            resolved = resolve_custom_llm_provider_ref(
                rp,
                capability=capability,
                model=rm,
            )
            return (
                resolved.provider,
                resolved.model,
                resolved.api_key,
                resolved.base_url,
                resolved.extra_request_headers,
                resolved.extra_request_body,
                list(resolved.fallback_models or ()) or None,
                resolved.cost_origin,
            )
        if rp is None and rm is None:
            resolved = resolve_llm_for_capability(capability, include_platform_default=True)
            if resolved is None:
                raise ValueError(
                    f"TextTransformService: platform default для capability={capability.value} "
                    + "не настроен"
                )
            return (
                resolved.provider,
                resolved.model,
                resolved.api_key,
                resolved.base_url,
                resolved.extra_request_headers,
                resolved.extra_request_body,
                list(resolved.fallback_models or ()) or None,
                resolved.cost_origin,
            )
        if rp is None or rm is None:
            raise ValueError(
                f"TextTransformService: для capability={capability.value} provider и model "
                + "должны быть заданы вместе"
            )
        return rp, rm, None, None, None, None, None, COST_ORIGIN_PLATFORM

    async def _prepare_llm_billing(
        self,
        *,
        cost_origin: str,
        model: str | None,
        provider: str | None,
        api_key: str | None,
        base_url: str | None,
    ) -> bool:
        if cost_origin == COST_ORIGIN_PLATFORM and should_use_platform_default_free_pool(
            model=model,
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            folder_id=None,
            settings=get_settings(),
        ):
            actx = get_context()
            if actx is None or actx.active_company is None:
                raise ValueError("TextTransformService: нужен Context с active_company (биллинг)")
            return await get_billing_service().company_may_incur_billable_operation_charge(
                actx.active_company.company_id
            )
        await self._require_llm_balance(cost_origin=cost_origin)
        return True

    async def _require_llm_balance(self, *, cost_origin: str = COST_ORIGIN_PLATFORM) -> None:
        actx = get_context()
        if actx is None or actx.active_company is None:
            raise ValueError("TextTransformService: нужен Context с active_company (биллинг)")
        if not str(actx.user.user_id).strip():
            raise ValueError("TextTransformService: нужен Context с user (биллинг)")
        await get_billing_service().require_balance_for_billable_operation(
            actx.active_company.company_id,
            str(actx.user.user_id).strip(),
            operation_code=BALANCE_BLOCK_OPERATION_LLM,
            notification_service="flows",
            cost_origin=cost_origin,
        )
