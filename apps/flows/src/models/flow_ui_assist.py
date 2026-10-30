"""AI-помощник редактора интерфейса: запрос и результат на той же грамматике блоков."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from core.models.base import StrictBaseModel
from core.ui_document.document import (
    FlowUIBlock,
    FlowUIBlockModel,
    FlowUIDocument,
    FlowUIPage,
    FlowUIPageId,
    iter_blocks,
)

FlowUIAssistScope = Literal["page", "block"]


class FlowUIAssistOutputError(Exception):
    """LLM вернул структурно валидный, но противоречащий документу результат."""


class FlowUIAssistRequest(StrictBaseModel):
    flow_id: str = Field(min_length=1)
    branch_id: str = Field(min_length=1)
    instruction: str = Field(min_length=1, max_length=4000)
    document: FlowUIDocument
    page_id: FlowUIPageId
    block_id: str | None = None

    @model_validator(mode="after")
    def _page_and_block_exist(self) -> FlowUIAssistRequest:
        page_ids = {page.page_id for page in self.document.pages}
        if self.page_id not in page_ids:
            raise ValueError(f"page {self.page_id!r} is not in the document")
        if self.block_id is not None and self.block_id not in {
            block.block_id for block in iter_blocks(self.page().blocks)
        }:
            raise ValueError(f"block {self.block_id!r} is not on page {self.page_id!r}")
        return self

    def page(self) -> FlowUIPage:
        return self.document.page(self.page_id)

    def selected_block(self) -> FlowUIBlockModel:
        if self.block_id is None:
            raise ValueError("selected_block requires block_id")
        return next(
            block for block in iter_blocks(self.page().blocks) if block.block_id == self.block_id
        )


class FlowUIAssistBlocks(StrictBaseModel):
    """Structured output для scope=block: блоки на замену выбранного."""

    blocks: list[FlowUIBlock] = Field(min_length=1, max_length=40)


class FlowUIAssistResult(StrictBaseModel):
    scope: FlowUIAssistScope
    page: FlowUIPage | None = None
    blocks: list[FlowUIBlock] = Field(default_factory=list)


__all__ = [
    "FlowUIAssistBlocks",
    "FlowUIAssistOutputError",
    "FlowUIAssistRequest",
    "FlowUIAssistResult",
    "FlowUIAssistScope",
]
