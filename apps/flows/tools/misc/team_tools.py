"""Platform team directory tools — company roster lookup for assign flows."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field

from apps.flows.src.tools.decorator import tool
from core.clients.team_client import TeamClient
from core.models import StrictBaseModel
from core.types import JsonObject

if TYPE_CHECKING:
    from apps.flows.src.state import ExecutionState

_TAGS = ["misc"]


class TeamListMembersArgs(StrictBaseModel):
    """Active company roster — no args."""


class TeamResolveUserArgs(StrictBaseModel):
    query: str = Field(
        ...,
        min_length=1,
        description=(
            "Имя или email (фрагмент) для поиска среди members активной компании. "
            "Не глобальный поиск по платформе."
        ),
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Максимум кандидатов (1–50).",
    )


@tool(
    name="team_list_members",
    description=(
        "Lists members of the active company (people and flow employees). "
        "Use before assigning a WorkItem to a person or adding someone to a work queue. "
        "Returns items[] with user_id, name, email, roles, is_flow_employee, flow_id. "
        "Not queue membership — that is work_queue_list_members."
    ),
    tags=_TAGS,
    parameters_model=TeamListMembersArgs,
    effects=["read"],
)
async def team_list_members(*, state: "ExecutionState") -> JsonObject:
    _ = state
    return {"items": await TeamClient().list_members()}


@tool(
    name="team_resolve_user",
    description=(
        "Finds company members by name/email substring (active company only). "
        "Use when the user says a display name like «Ivan» before work_item_assign/create. "
        "If matches length is 0 or >1 — ask_user to disambiguate; never invent user_id. "
        "Returns matches[] with user_id, name, email, is_flow_employee, flow_id."
    ),
    tags=_TAGS,
    parameters_model=TeamResolveUserArgs,
    effects=["read"],
)
async def team_resolve_user(
    query: str,
    limit: int = 10,
    *,
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    args = TeamResolveUserArgs(query=query, limit=limit)
    matches = await TeamClient().resolve_user(args.query, limit=args.limit)
    return {
        "query": args.query,
        "matches": matches,
        "match_count": len(matches),
    }
