"""Применение ui-событий агента к ``ExecutionState``.

Именованный slot хранит последний рендер в ``state.ui_slots`` (frozen, не проецируется
в артефакт ``state``); ``conversation`` — лента, в state не копится. Само событие
встаёт в очередь публикации и уходит артефактом ``ui`` в ближайшей точке flush runtime.
"""

from __future__ import annotations

from apps.flows.src.state.execution_state import ExecutionState
from core.ui_document.document import (
    FlowUIBlock,
    FlowUIBlockId,
    FlowUIConversation,
    FlowUIDocument,
    FlowUIPageId,
    FlowUISlot,
    assert_unique_block_ids,
    iter_blocks,
)
from core.ui_document.protocol import CONVERSATION_SLOT_ID, FlowUINavigate, FlowUIRender


def slot_ids(document: FlowUIDocument) -> set[str]:
    """Цели рендера интерфейса: все ``slot`` плюс всегда доступная ``conversation``."""
    ids: set[str] = {CONVERSATION_SLOT_ID}
    for page in document.pages:
        for block in iter_blocks(page.blocks):
            if isinstance(block, FlowUISlot):
                ids.add(block.block_id)
    return ids


def apply_ui_render(state: ExecutionState, render: FlowUIRender) -> None:
    for block in iter_blocks(list(render.blocks)):
        if isinstance(block, FlowUISlot | FlowUIConversation):
            raise ValueError(
                f"{block.type} {block.block_id!r} is a render target and cannot be rendered"
            )
    if render.slot_id != CONVERSATION_SLOT_ID:
        assert_unique_block_ids(render.blocks, scope=f"slot {render.slot_id!r}")
        state.ui_slots = {**state.ui_slots, render.slot_id: list(render.blocks)}
    state.queue_ui_events([render])


def apply_ui_navigate(state: ExecutionState, navigate: FlowUINavigate) -> None:
    state.queue_ui_events([navigate])


def render_conversation(state: ExecutionState, blocks: list[FlowUIBlock]) -> FlowUIRender:
    """Карточка в ленту: платформенные tools показывают результат типизированными блоками."""
    render = FlowUIRender(slot_id=CONVERSATION_SLOT_ID, blocks=blocks)
    apply_ui_render(state, render)
    return render


def assert_known_slot(document: FlowUIDocument, slot_id: FlowUIBlockId) -> None:
    known = slot_ids(document)
    if slot_id not in known:
        raise ValueError(f"unknown slot_id {slot_id!r}; available: {sorted(known)}")


def assert_known_page(document: FlowUIDocument, page_id: FlowUIPageId) -> None:
    known = [page.page_id for page in document.pages]
    if page_id not in known:
        raise ValueError(f"unknown page_id {page_id!r}; available: {known}")


__all__ = [
    "apply_ui_navigate",
    "apply_ui_render",
    "assert_known_page",
    "assert_known_slot",
    "render_conversation",
    "slot_ids",
]
