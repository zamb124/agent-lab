"""
Демо-очередь HITL (WorkQueue) для примеров в bundles (example_react, example_graph).
"""

from core.worktracker.service import WorkItemService

EXAMPLE_HITL_SLUG = "example_hitl"


async def ensure_example_hitl_queue(work_item_service: WorkItemService, company_id: str) -> None:
    for queue in await work_item_service.list_queues(company_id):
        if queue.work_queue_slug == EXAMPLE_HITL_SLUG:
            return
    _ = await work_item_service.create_queue(
        company_id=company_id,
        name="Demo HITL (example_hitl)",
        slug=EXAMPLE_HITL_SLUG,
        description=(
            "Демо-очередь для сценариев HITL в example_react и example_graph. "
            "Назначьте операторов через API или интерфейс."
        ),
    )
