"""FGA company/group seed + Context for in-process tool execution (OpenFGA sole PDP)."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Sequence

from core.authz.company_sync import sync_company_member_roles
from core.authz.group_sync import sync_user_groups
from core.authz.models import AuthzObject
from core.context import clear_context, set_context
from core.models.context_models import Context
from core.models.identity_models import Company, User

_TOOL_TEST_COMPANY_ID = "system"
_TOOL_TEST_USER_IDS: tuple[str, ...] = (
    "u1",
    "user-1",
    "tool_test_user",
    "test_user",
    "system",
    "test",
    "test-user-1",
    "test-user",
)


async def bind_flow_tool_authz_context(
    extra_user_ids: Sequence[str] = (),
    *,
    di,
) -> AsyncIterator[None]:
    """Seed company/group membership so BaseTool.run reaches _run_impl via OpenFGA."""
    set_context(
        Context(
            user=User(user_id="u1", name="Tool Test User"),
            active_company=Company(
                company_id=_TOOL_TEST_COMPANY_ID,
                name="System",
            ),
            session_id="tool-test",
            channel="test",
        )
    )
    user_ids = list(dict.fromkeys([*_TOOL_TEST_USER_IDS, *extra_user_ids]))
    for user_id in user_ids:
        await sync_company_member_roles(
            di.authz_service,
            company_id=_TOOL_TEST_COMPANY_ID,
            user_id=user_id,
            roles=["owner", "admin"],
        )
        await sync_user_groups(
            di.authz_service,
            user_id=user_id,
            groups=["admin", "developers"],
            company_ids=[_TOOL_TEST_COMPANY_ID],
            previous_groups=[],
        )
    # MINIMIZE_LATENCY: свежая запись видна check с суб-секундным лагом —
    # ждём, пока та же консистентность начнёт возвращать can_admin, иначе
    # первый op_* после сида ловит устаревший deny.
    company = AuthzObject.company(_TOOL_TEST_COMPANY_ID)
    deadline = time.monotonic() + 10.0
    pending = set(user_ids)
    while pending:
        for user_id in tuple(pending):
            if await di.authz_service.can_admin(company, user_id=user_id):
                pending.discard(user_id)
        if not pending:
            break
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"openfga can_admin visibility timeout: {sorted(pending)} on {company.fga_id}"
            )
        await asyncio.sleep(0.05)
    try:
        yield
    finally:
        clear_context()
