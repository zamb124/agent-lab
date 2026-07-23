"""Platform team directory tools — company roster lookup for assign flows."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field

from apps.flows.src.container_state import require_current_container
from apps.flows.src.tools.decorator import tool
from core.context import require_active_company
from core.identity.flow_employee import (
    is_flow_employee,
    require_flow_employee_flow_id,
)
from core.models import StrictBaseModel
from core.types import JsonObject

if TYPE_CHECKING:
    from core.state import ExecutionState

_TAGS = ["misc", "platform", "team"]


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


def _member_brief(
    *,
    user_id: str,
    name: str,
    email: str | None,
    roles: list[str],
    is_employee: bool,
    flow_id: str | None,
) -> JsonObject:
    return {
        "user_id": user_id,
        "name": name,
        "email": email,
        "roles": roles,
        "is_flow_employee": is_employee,
        "flow_id": flow_id,
    }


async def _company_member_rows() -> list[JsonObject]:
    company_id = require_active_company().company_id
    container = require_current_container()
    stored_company = await container.company_repository.get(company_id)
    if stored_company is None:
        raise ValueError(f"Company {company_id!r} не найдена")
    rows: list[JsonObject] = []
    for user_id, roles in stored_company.members.items():
        member_user = await container.user_repository.get(user_id)
        if member_user is None:
            continue
        member_email = member_user.emails[0] if member_user.emails else None
        member_is_employee = is_flow_employee(member_user)
        rows.append(
            _member_brief(
                user_id=user_id,
                name=member_user.name,
                email=member_email,
                roles=list(roles),
                is_employee=member_is_employee,
                flow_id=(
                    require_flow_employee_flow_id(member_user)
                    if member_is_employee
                    else None
                ),
            )
        )
    return rows


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
)
async def team_list_members(*, state: "ExecutionState") -> JsonObject:
    _ = state
    return {"items": await _company_member_rows()}


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
)
async def team_resolve_user(
    query: str,
    limit: int = 10,
    *,
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    args = TeamResolveUserArgs(query=query, limit=limit)
    needle = args.query.strip().casefold()
    if needle == "":
        raise ValueError("query обязателен (имя или email)")
    matches: list[JsonObject] = []
    for row in await _company_member_rows():
        name = str(row["name"]).casefold()
        email_raw = row["email"]
        email = str(email_raw).casefold() if isinstance(email_raw, str) else ""
        if needle in name or (email != "" and needle in email):
            matches.append(row)
        if len(matches) >= args.limit:
            break
    return {
        "query": args.query,
        "matches": matches,
        "match_count": len(matches),
    }
