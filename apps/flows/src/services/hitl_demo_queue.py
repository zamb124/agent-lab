"""
Демо-очередь HITL (WorkQueue) для примеров в bundles (example_react, example_graph).

Создаёт очередь `example_hitl` и гарантирует членство company owner/admin —
иначе claim/complete недоступны и ответ оператора не уходит в user chat.
"""

from core.models.identity_models import Company
from core.worktracker.models import UserActor
from core.worktracker.service import WorkItemService

EXAMPLE_HITL_SLUG = "example_hitl"


def hitl_demo_operator_user_ids(company: Company) -> list[str]:
    """Owner + members с ролью admin/owner — операторы демо-очереди."""
    user_ids: list[str] = []
    owner = company.owner_user_id
    if owner is not None and owner.strip() != "":
        user_ids.append(owner.strip())
    for user_id, roles in company.members.items():
        if user_id.strip() == "":
            continue
        if "admin" not in roles and "owner" not in roles:
            continue
        cleaned = user_id.strip()
        if cleaned not in user_ids:
            user_ids.append(cleaned)
    return user_ids


async def ensure_example_hitl_queue(
    work_item_service: WorkItemService,
    company_id: str,
    *,
    member_user_ids: list[str] | None = None,
) -> None:
    queue = None
    for existing in await work_item_service.list_queues(company_id):
        if existing.work_queue_slug == EXAMPLE_HITL_SLUG:
            queue = existing
            break

    members = [uid.strip() for uid in (member_user_ids or []) if uid.strip()]
    if queue is None:
        creator = UserActor(user_id=members[0]) if members else None
        queue = await work_item_service.create_queue(
            company_id=company_id,
            name="Demo HITL (example_hitl)",
            slug=EXAMPLE_HITL_SLUG,
            description=(
                "Демо-очередь для сценариев HITL в example_react и example_graph. "
                "Owner/admin компании добавляются автоматически при ensure."
            ),
            creator=creator,
        )
        # create_queue уже добавил creator; остальных — ниже
        members = members[1:] if creator is not None else members

    for user_id in members:
        actor = UserActor(user_id=user_id)
        if await work_item_service.is_member(queue.work_queue_id, actor):
            continue
        _ = await work_item_service.add_queue_member(
            company_id=company_id,
            work_queue_id=queue.work_queue_id,
            member=actor,
            role="member",
        )
