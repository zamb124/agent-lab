"""Builtin tools WorkQueue для flow-employee / Lara."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import Field

from apps.flows.src.services.platform_facades import get_work_item_service
from apps.flows.src.tools.decorator import tool
from core.context import require_active_company, require_context
from core.models import StrictBaseModel
from core.types import JsonObject
from core.worktracker.models import UserActor, WorkActor

if TYPE_CHECKING:
    from core.state import ExecutionState

_TAGS = ["worktracker"]


class WorkQueueListArgs(StrictBaseModel):
    """Без фильтров — все очереди компании."""


class WorkQueueGetBySlugArgs(StrictBaseModel):
    work_queue_slug: str = Field(
        ...,
        min_length=1,
        description="Slug очереди (уникален в компании). Не выдумывай — бери из list.",
    )


class WorkQueueCreateArgs(StrictBaseModel):
    name: str = Field(..., min_length=1, description="Отображаемое имя очереди.")
    work_queue_slug: str = Field(
        ...,
        min_length=1,
        description="Уникальный slug (латиница/цифры/_). Станет work_queue_slug.",
    )
    description: str | None = Field(
        default=None,
        description="Описание очереди. Omit/null — без описания.",
    )


class WorkQueueUpdateArgs(StrictBaseModel):
    work_queue_id: str = Field(..., min_length=1, description="work_queue_id из list/get.")
    name: str | None = Field(default=None, description="Новое имя. Omit — не менять.")
    description: str | None = Field(
        default=None,
        description="Новое описание. Omit — не менять.",
    )


class WorkQueueMembersListArgs(StrictBaseModel):
    work_queue_id: str = Field(
        ...,
        min_length=1,
        description="work_queue_id. Это участники ОЧЕРЕДИ, не команда компании (team_list_members).",
    )


class WorkQueueMemberAddArgs(StrictBaseModel):
    work_queue_id: str = Field(..., min_length=1, description="work_queue_id очереди.")
    user_id: str = Field(
        ...,
        min_length=1,
        description=(
            "user_id человека или flow_employee_* из team_list_members / team_resolve_user. "
            "Не выдумывай."
        ),
    )
    role: Literal["member", "owner"] = Field(
        default="member",
        description="Роль в очереди: member | owner.",
    )


class WorkQueueMemberRemoveArgs(StrictBaseModel):
    work_queue_id: str = Field(..., min_length=1, description="work_queue_id очереди.")
    user_id: str = Field(
        ...,
        min_length=1,
        description="user_id участника для удаления из очереди.",
    )


def _queue_brief(queue_id: str, name: str, slug: str, description: str | None) -> JsonObject:
    return {
        "work_queue_id": queue_id,
        "name": name,
        "work_queue_slug": slug,
        "description": description,
    }


@tool(
    name="work_queue_list",
    description=(
        "Lists WorkQueues in the active company. "
        "Use before assign-to-queue or to discover work_queue_slug / work_queue_id. "
        "Returns items[] with work_queue_id, name, work_queue_slug, description."
    ),
    tags=_TAGS,
    parameters_model=WorkQueueListArgs,
)
async def work_queue_list(*, state: "ExecutionState") -> JsonObject:
    _ = state
    queues = await get_work_item_service().list_queues(require_active_company().company_id)
    return {
        "items": [
            _queue_brief(q.work_queue_id, q.name, q.work_queue_slug, q.description)
            for q in queues
        ]
    }


@tool(
    name="work_queue_get_by_slug",
    description=(
        "Resolves a WorkQueue by work_queue_slug. "
        "Use when the user names a queue slug before create/assign/claim. "
        "Returns work_queue_id, name, work_queue_slug, description."
    ),
    tags=_TAGS,
    parameters_model=WorkQueueGetBySlugArgs,
)
async def work_queue_get_by_slug(
    work_queue_slug: str,
    *,
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    args = WorkQueueGetBySlugArgs(work_queue_slug=work_queue_slug)
    queue = await get_work_item_service().get_queue_by_slug(
        require_active_company().company_id,
        args.work_queue_slug,
    )
    return _queue_brief(
        queue.work_queue_id, queue.name, queue.work_queue_slug, queue.description
    )


@tool(
    name="work_queue_create",
    description=(
        "Creates a WorkQueue and adds the current user as owner member. "
        "Slug must be unique in the company. Returns the created queue summary."
    ),
    tags=_TAGS,
    parameters_model=WorkQueueCreateArgs,
)
async def work_queue_create(
    name: str,
    work_queue_slug: str,
    description: str | None = None,
    *,
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    args = WorkQueueCreateArgs(
        name=name,
        work_queue_slug=work_queue_slug,
        description=description,
    )
    queue = await get_work_item_service().create_queue(
        company_id=require_active_company().company_id,
        name=args.name,
        slug=args.work_queue_slug,
        description=args.description,
        creator=UserActor(user_id=require_context().user.user_id),
    )
    return _queue_brief(
        queue.work_queue_id, queue.name, queue.work_queue_slug, queue.description
    )


@tool(
    name="work_queue_update",
    description=(
        "Updates WorkQueue name and/or description by work_queue_id. "
        "Omit fields you do not change. Returns updated queue summary."
    ),
    tags=_TAGS,
    parameters_model=WorkQueueUpdateArgs,
)
async def work_queue_update(
    work_queue_id: str,
    name: str | None = None,
    description: str | None = None,
    *,
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    args = WorkQueueUpdateArgs(
        work_queue_id=work_queue_id,
        name=name,
        description=description,
    )
    queue = await get_work_item_service().update_queue(
        company_id=require_active_company().company_id,
        work_queue_id=args.work_queue_id,
        name=args.name,
        description=args.description,
    )
    return _queue_brief(
        queue.work_queue_id, queue.name, queue.work_queue_slug, queue.description
    )


@tool(
    name="work_queue_list_members",
    description=(
        "Lists members of a WorkQueue (who may claim queue tasks). "
        "Not the company roster — use team_list_members for company people. "
        "Returns items[] with user_id (member_ref), role."
    ),
    tags=_TAGS,
    parameters_model=WorkQueueMembersListArgs,
)
async def work_queue_list_members(
    work_queue_id: str,
    *,
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    args = WorkQueueMembersListArgs(work_queue_id=work_queue_id)
    members = await get_work_item_service().list_queue_members(args.work_queue_id)
    items: list[JsonObject] = []
    for member in members:
        actor: WorkActor = member.member
        if not isinstance(actor, UserActor):
            raise TypeError(f"Unexpected queue member actor: {type(actor)!r}")
        items.append(
            {
                "work_queue_id": member.work_queue_id,
                "user_id": actor.user_id,
                "role": member.role,
            }
        )
    return {"items": items}


@tool(
    name="work_queue_add_member",
    description=(
        "Adds a company user or flow_employee to a WorkQueue. "
        "Resolve user_id via team_list_members / team_resolve_user first. "
        "Returns work_queue_id, user_id, role."
    ),
    tags=_TAGS,
    parameters_model=WorkQueueMemberAddArgs,
)
async def work_queue_add_member(
    work_queue_id: str,
    user_id: str,
    role: Literal["member", "owner"] = "member",
    *,
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    args = WorkQueueMemberAddArgs(
        work_queue_id=work_queue_id,
        user_id=user_id,
        role=role,
    )
    member = await get_work_item_service().add_queue_member(
        company_id=require_active_company().company_id,
        work_queue_id=args.work_queue_id,
        member=UserActor(user_id=args.user_id),
        role=args.role,
    )
    actor = member.member
    if not isinstance(actor, UserActor):
        raise TypeError(f"Unexpected queue member actor: {type(actor)!r}")
    return {
        "work_queue_id": member.work_queue_id,
        "user_id": actor.user_id,
        "role": member.role,
    }


@tool(
    name="work_queue_remove_member",
    description=(
        "Removes a member from a WorkQueue by user_id. "
        "Returns removed=true when the member existed."
    ),
    tags=_TAGS,
    parameters_model=WorkQueueMemberRemoveArgs,
)
async def work_queue_remove_member(
    work_queue_id: str,
    user_id: str,
    *,
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    args = WorkQueueMemberRemoveArgs(work_queue_id=work_queue_id, user_id=user_id)
    removed = await get_work_item_service().remove_queue_member(
        work_queue_id=args.work_queue_id,
        member=UserActor(user_id=args.user_id),
    )
    return {
        "work_queue_id": args.work_queue_id,
        "user_id": args.user_id,
        "removed": removed,
    }
