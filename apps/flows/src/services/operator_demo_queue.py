"""
Демо-очередь оператора для примеров HITL в bundles (example_react, example_graph).
"""

from apps.flows.src.db.operator_repository import OperatorRepository

EXAMPLE_HITL_SLUG = "example_hitl"


async def ensure_example_hitl_queue(repository: OperatorRepository, company_id: str) -> None:
    if await repository.get_queue_by_slug(company_id, EXAMPLE_HITL_SLUG) is not None:
        return
    _ = await repository.create_queue(
        company_id=company_id,
        name="Demo HITL (example_hitl)",
        slug=EXAMPLE_HITL_SLUG,
        description=(
            "Демо-очередь для сценариев HITL в example_react и example_graph. "
            "Назначьте операторов через API или интерфейс."
        ),
    )
