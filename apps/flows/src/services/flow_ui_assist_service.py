"""AI-помощник редактора интерфейса: «Описать страницу» и «Изменить выбранный блок».

LLM отвечает structured output по Pydantic-грамматике (``FlowUIPage`` или ``FlowUIAssistBlocks``),
поэтому невалидный интерфейс физически не может попасть в документ; результат редактор
вставляет как обычную команду истории.
"""

from __future__ import annotations

from apps.flows.src.models.flow_ui_assist import (
    FlowUIAssistBlocks,
    FlowUIAssistOutputError,
    FlowUIAssistRequest,
    FlowUIAssistResult,
)
from apps.flows.src.state.mutation_policy import FROZEN_STATE_FIELDS
from core.ai.providers import AICapability
from core.ai.requirements import AIRequestRequirements
from core.ai.resolver import resolve_ai_model
from core.ai.runtime import create_llm_client_from_ai_model
from core.billing.service import BillingService
from core.clients.llm.client import LLMClient
from core.clients.llm.mock import MockLLM
from core.ui_document.document import FlowUIPage, iter_blocks

GRAMMAR_RULES = "\n".join(
    [
        "Flow UI grammar rules:",
        "- Every block has a unique snake/kebab-case block_id and a type from the schema.",
        "- Input blocks write to state via `field`; never use system fields: "
        + ", ".join(sorted(FROZEN_STATE_FIELDS))
        + ".",
        "- Text properties are templates: `{path}` inserts a state value, `{?path}` is optional.",
        "- A page with input blocks needs a button whose action.name names the submitted action.",
        "- Prefer platform blocks (heading, text, text_input, select, button, metric, data_table, columns, "
        + "section) over html; use html only for custom widgets.",
        "- Keep the same language as the instruction for user-facing texts.",
    ]
)


class FlowUIAssistService:
    def __init__(self, billing_service: BillingService) -> None:
        self._billing_service: BillingService = billing_service

    async def assist(self, request: FlowUIAssistRequest) -> FlowUIAssistResult:
        if request.block_id is None:
            return await self._describe_page(request, request.page())
        return await self._rewrite_block(request, request.page())

    def _llm(self) -> LLMClient | MockLLM:
        resolved = resolve_ai_model(
            AICapability.LLM_CHAT,
            AIRequestRequirements(structured_output=True, quality_preference="highest"),
            include_platform_default=True,
        )
        if resolved is None:
            raise ValueError(
                "flow_ui_assist: platform default for capability=llm_chat not configured"
            )
        return create_llm_client_from_ai_model(
            resolved, billing_service=self._billing_service
        )

    async def _describe_page(
        self, request: FlowUIAssistRequest, page: FlowUIPage
    ) -> FlowUIAssistResult:
        prompt = (
            f"{GRAMMAR_RULES}\n\n"
            f"Current page (JSON):\n{page.model_dump_json()}\n\n"
            f"Instruction: {request.instruction}\n\n"
            f"Return the full updated page with page_id {page.page_id!r}."
        )
        result = await self._llm().chat(prompt, response_model=FlowUIPage)
        if result.page_id != page.page_id:
            raise FlowUIAssistOutputError(f"page_id changed to {result.page_id!r}")
        return FlowUIAssistResult(scope="page", page=result)

    async def _rewrite_block(
        self, request: FlowUIAssistRequest, page: FlowUIPage
    ) -> FlowUIAssistResult:
        selected = request.selected_block()
        taken = sorted(
            block.block_id
            for block in iter_blocks(page.blocks)
            if block.block_id != selected.block_id
        )
        prompt = (
            f"{GRAMMAR_RULES}\n\n"
            f"Page (JSON, for context):\n{page.model_dump_json()}\n\n"
            f"Selected block (JSON):\n{selected.model_dump_json()}\n\n"
            f"Instruction: {request.instruction}\n\n"
            "Return the blocks that replace the selected block (usually one). "
            f"block_id values already used on the page: {', '.join(taken) if taken else '(none)'}."
        )
        result = await self._llm().chat(prompt, response_model=FlowUIAssistBlocks)
        for block in result.blocks:
            if block.block_id in taken:
                raise FlowUIAssistOutputError(
                    f"block_id {block.block_id!r} collides with an existing block"
                )
        return FlowUIAssistResult(scope="block", blocks=result.blocks)


__all__ = ["FlowUIAssistService"]
