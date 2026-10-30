"""Чтение блоков, которые тулы отрендерили в ленту.

Платформенные результаты (skill load, action preview/apply, browser preview, handoff)
попадают в ленту как типизированные блоки грамматики через ``ui_render`` в ``conversation``.
До точки flush runtime события лежат в очереди state — тесты читают ровно то, что уйдёт
клиенту артефактом ``ui``.
"""

from __future__ import annotations

from apps.flows.src.state import ExecutionState
from core.ui_document.document import FlowUIBlockModel, iter_blocks
from core.ui_document.protocol import CONVERSATION_SLOT_ID, FlowUIRender


def conversation_blocks(
    state: ExecutionState, *, block_type: str | None = None
) -> list[FlowUIBlockModel]:
    """Блоки ленты в порядке рендера; ``block_type`` фильтрует по дискриминатору."""
    blocks: list[FlowUIBlockModel] = []
    for event in state.pending_ui_events():
        if not isinstance(event, FlowUIRender) or event.slot_id != CONVERSATION_SLOT_ID:
            continue
        for block in iter_blocks(list(event.blocks)):
            if block_type is None or block.type == block_type:
                blocks.append(block)
    return blocks


def conversation_block(state: ExecutionState, block_id: str) -> FlowUIBlockModel:
    for block in conversation_blocks(state):
        if block.block_id == block_id:
            return block
    known = [block.block_id for block in conversation_blocks(state)]
    raise AssertionError(f"conversation block {block_id!r} not found; present: {known!r}")


__all__ = ["conversation_block", "conversation_blocks"]
