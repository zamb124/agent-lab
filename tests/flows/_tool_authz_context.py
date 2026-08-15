"""FGA company/group seed + Context for in-process tool execution (OpenFGA sole PDP)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

from apps.flows.src.container import get_container
from core.authz.company_sync import sync_company_member_roles
from core.authz.group_sync import sync_user_groups
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
    container = get_container()
    user_ids = list(dict.fromkeys([*_TOOL_TEST_USER_IDS, *extra_user_ids]))
    for user_id in user_ids:
        await sync_company_member_roles(
            container.authz_service,
            company_id=_TOOL_TEST_COMPANY_ID,
            user_id=user_id,
            roles=["owner", "admin"],
        )
        await sync_user_groups(
            container.authz_service,
            user_id=user_id,
            groups=["admin", "developers"],
            company_ids=[_TOOL_TEST_COMPANY_ID],
            previous_groups=[],
        )
    try:
        yield
    finally:
        clear_context()
