"""
Источник LLM-контекста по задачам WorkItem.

Точка интеграции «широкой памяти»: активные задачи компании (открытые и в работе)
подаются в общий LLM context layer как `kind=memory` блок, чтобы агенты видели
текущую работу и лишний раз не переспрашивали. Подключается в
`LLMContextSourceRegistry` наряду с memory/RAG источниками.
"""

from __future__ import annotations

import hashlib

from core.context import get_context
from core.llm_context.models import LLMContextBlock
from core.llm_context.sources import LLMContextSourceRequest
from core.worktracker.models import TERMINAL_WORK_ITEM_STATES
from core.worktracker.service import WorkItemService

_MAX_ITEMS = 20


class WorkItemLLMContextSource:
    """Активные задачи WorkItem компании как memory-блок контекста."""

    name: str = "memory.work_items"

    def __init__(self, work_item_service: WorkItemService) -> None:
        self._work_items: WorkItemService = work_item_service

    async def collect(self, request: LLMContextSourceRequest) -> list[LLMContextBlock]:
        _ = request
        context = get_context()
        if context is None or context.active_company is None:
            return []
        company_id = context.active_company.company_id
        items = await self._work_items.list(company_id, limit=_MAX_ITEMS)
        active = [item for item in items if item.state not in TERMINAL_WORK_ITEM_STATES]
        if not active:
            return []
        lines = [
            f"- [{item.state.value}] {item.title} (id={item.work_item_id}, kind={item.kind.value})"
            for item in active
        ]
        content = "[Активные задачи команды]\n" + "\n".join(lines)
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        return [
            LLMContextBlock(
                kind="memory",
                budget_scope="memory",
                role="system",
                content=content,
                stable_key=f"memory:work_items:{company_id}:{digest}",
                provenance={"source": self.name, "company_id": company_id},
            )
        ]


__all__ = ["WorkItemLLMContextSource"]
