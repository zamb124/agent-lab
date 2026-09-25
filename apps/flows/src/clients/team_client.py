"""TeamClient — roster активной компании для team_* tools."""

from __future__ import annotations

from core.context import require_active_company
from core.identity.flow_employee import (
    is_flow_employee,
    require_flow_employee_flow_id,
)
from core.models.identity_models import Company, User
from core.types import JsonObject


class TeamClient:
    """Члены компании и resolve по имени/email."""

    def _member_brief(
        self,
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

    async def list_members(self) -> list[JsonObject]:
        company_id = require_active_company().company_id
        stored_company = await Company.get(company_id)
        if stored_company is None:
            raise ValueError(f"Company {company_id!r} not found")
        rows: list[JsonObject] = []
        for user_id, roles in stored_company.members.items():
            member_user = await User.get(user_id)
            if member_user is None:
                continue
            member_email = member_user.emails[0] if member_user.emails else None
            member_is_employee = is_flow_employee(member_user)
            rows.append(
                self._member_brief(
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

    async def resolve_user(self, query: str, *, limit: int = 10) -> list[JsonObject]:
        needle = query.strip().casefold()
        if needle == "":
            raise ValueError("query is required (name or email)")
        if limit < 1:
            raise ValueError("limit must be >= 1")
        matches: list[JsonObject] = []
        for row in await self.list_members():
            name = str(row["name"]).casefold()
            email_raw = row["email"]
            email = str(email_raw).casefold() if isinstance(email_raw, str) else ""
            if needle in name or (email != "" and needle in email):
                matches.append(row)
            if len(matches) >= limit:
                break
        return matches
