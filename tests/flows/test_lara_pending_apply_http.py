"""LaraFacade.apply_pending_action_from_http без LLM-повтора (контур embed)."""

from __future__ import annotations

import json

import pytest
import pytest_asyncio

from apps.flows.src.container import get_container
from apps.flows.tools.lara_crm import crm_create_note
from core.state import ExecutionState

pytestmark = [
    pytest.mark.timeout(120, func_only=True),
]


@pytest_asyncio.fixture
async def lara_crm_tool_context(
    crm_client,
    auth_token_system,
    system_user_id,
    unique_id,
):
    from core.context import set_context
    from core.models.context_models import Context
    from core.models.identity_models import Company, User

    ctx = Context(
        user=User(user_id=system_user_id, name="Lara pending apply HTTP"),
        active_company=Company(company_id="system", name="System"),
        auth_token=auth_token_system,
        channel="test",
        active_namespace="default",
        metadata={"user_id": system_user_id, "email": "test@example.com", "grps": []},
    )
    set_context(ctx)
    return ctx


def _tool_state(*, unique_id: str, system_user_id: str) -> ExecutionState:
    return ExecutionState.create(
        task_id=f"lara-pending-{unique_id}",
        context_id=f"embed-ctx-{unique_id}",
        user_id=system_user_id,
        session_id=f"lara:pending:{unique_id}",
    )


@pytest.mark.asyncio
async def test_apply_pending_http_creates_note(
    crm_service,
    lara_crm_tool_context,
    unique_id: str,
    system_user_id: str,
) -> None:
    state = _tool_state(unique_id=unique_id, system_user_id=system_user_id)
    propose_raw = await crm_create_note._run_impl(
        {"name": f"HTTP apply {unique_id}", "description": "body", "mode": "propose"},
        state,
    )
    proposed = json.loads(propose_raw)
    pid = proposed["pending_action_id"]
    facade = get_container().lara_facade
    applied = await facade.apply_pending_action_from_http(
        pending_action_id=pid,
        context_id=state.context_id,
        idempotency_key=None,
    )
    assert applied.status == "applied"
    res = applied.result
    assert res is not None, applied
    ent = res.get("entity")
    assert isinstance(ent, dict) and ent.get("entity_id")
