"""Сервис суммаризации и форматирования текста через платформенные LLM capabilities."""

from __future__ import annotations

from a2a.helpers.proto_helpers import get_message_text
from a2a.types import Message, Part, Role

from core.ai.models import ResolvedAIModel
from core.ai.providers import AICapability, split_provider_prefixed_model
from core.ai.requirements import AISelection
from core.ai.resolver import resolve_ai_model
from core.ai.runtime import create_llm_client_from_ai_model
from core.clients.llm.messages import build_a2a_message
from core.config import get_settings
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

    Форматирование Markdown всегда идёт через ``AICapability.LLM_FORMAT_MARKDOWN``.
    LitServe не является LLM-провайдером для markdown.
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
            raise ValueError('summarize: text is empty')

        resolved = self._resolve_company_llm_args(
            AICapability.LLM_SUMMARIZE,
            provider=provider,
            model=model,
        )
        llm = create_llm_client_from_ai_model(
            resolved,
            max_tokens=max_output_tokens,
        )
        sys_text = instruction.strip() if instruction is not None and instruction.strip() else _DEFAULT_SUMMARY_INSTRUCTION
        messages: list[Message] = [
            build_a2a_message(
                role=Role.ROLE_USER,
                parts=[Part(text=sys_text + "\n\n" + stripped)],
            ),
        ]
        out = await llm.chat(messages, llm_context=_INTERNAL_TEXT_TRANSFORM_LLM_CONTEXT)
        summary = get_message_text(out).strip()
        if not summary:
            raise ValueError('summarize: empty model response')
        return summary

    async def format_markdown(
        self,
        text: str,
    ) -> str:
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

        llm = create_llm_client_from_ai_model(resolved)
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
