"""
Демо-очередь HITL (WorkQueue) для примеров в bundles (example_react, example_graph).

Создаёт очередь `example_hitl` и гарантирует членство company admins из OpenFGA —
иначе claim/complete недоступны и ответ оператора не уходит в user chat.
"""

from core.authz.models import AuthzObject
from core.authz.service import AuthzService
from core.authz.types import AuthzRelation, AuthzSubjectKind
from core.logging import get_logger
from core.worktracker.models import UserActor
from core.worktracker.service import WorkItemService

EXAMPLE_HITL_SLUG = "example_hitl"

logger = get_logger(__name__)


async def hitl_demo_operator_user_ids(authz: AuthzService, company_id: str) -> list[str]:
    """Пользователи с company can_admin (OpenFGA) — операторы демо-очереди."""
    subjects = await authz.list_users(
        AuthzObject.company(company_id),
        AuthzRelation.CAN_ADMIN,
    )
    user_ids = sorted(
        {
            subject.value.strip()
            for subject in subjects
            if subject.kind is AuthzSubjectKind.USER and subject.value.strip() != ""
        }
    )
    return user_ids


async def ensure_example_hitl_queue(
    work_item_service: WorkItemService,
    company_id: str,
    *,
    member_user_ids: list[str] | None = None,
) -> None:
    queue = None
    try:
        queue = await work_item_service.get_queue_by_slug(company_id, EXAMPLE_HITL_SLUG)
    except ValueError:
        queue = None

    members = [uid.strip() for uid in (member_user_ids or []) if uid.strip()]
    if queue is None:
        if not members:
            logger.info(
                "hitl_demo.queue_skipped_no_admin",
                company_id=company_id,
                slug=EXAMPLE_HITL_SLUG,
            )
            return
        creator = UserActor(user_id=members[0])
        queue = await work_item_service.create_queue(
            company_id=company_id,
            name="Demo HITL (example_hitl)",
            slug=EXAMPLE_HITL_SLUG,
            description=(
                "Демо-очередь для сценариев HITL в example_react и example_graph. "
                "Company admins добавляются автоматически при ensure."
            ),
            creator=creator,
        )
        members = members[1:]

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
