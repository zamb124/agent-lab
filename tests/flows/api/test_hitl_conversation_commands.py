"""Prod-like: HITL conversation — REST и `op_*` один handler."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

import pytest
from httpx2 import AsyncClient

from apps.flows.di import FlowsDi
from apps.flows.realtime.hitl_operations import (
    op_flows_hitl_conversation_get,
    op_flows_hitl_conversation_send,
)
from apps.flows.src.models.hitl_conversation import (
    HitlConversationWorkItemPayload,
    OperatorMessageRequest,
)
from apps.flows.src.state.interrupt import HandoffMode
from core.context import reset_context, set_context
from core.models.context_models import Context
from core.models.identity_models import User
from core.websocket import WsCommandError
from tests.fixtures.ai_provider_defaults import make_test_company
from tests.flows.hitl_test_harness import park_hitl_session

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(60, func_only=True)]

HITL_API = "/flows/api/v1/hitl"


@contextmanager
def _system_scope(system_user_id: str) -> Generator[User]:
    user = User(user_id=system_user_id, name="System")
    token = set_context(
        Context(
            user=user,
            active_company=make_test_company(company_id="system", name="System"),
            channel="api",
            active_namespace="default",
        )
    )
    try:
        yield user
    finally:
        reset_context(token)


async def test_hitl_conversation_get_rest_match_op(
    client: AsyncClient,
    di: FlowsDi,
    worktracker_di: object,
    unique_id: str,
    system_user_id: str,
) -> None:
    _ = worktracker_di
    parked = await park_hitl_session(
        di, unique_id, mode=HandoffMode.TAKEOVER, owner_user_id=system_user_id
    )
    http = await client.get(f"{HITL_API}/{parked.work_item_id}/conversation")
    assert http.status_code == 200, http.text
    with _system_scope(system_user_id) as user:
        op_result = await op_flows_hitl_conversation_get(
            HitlConversationWorkItemPayload(work_item_id=parked.work_item_id),
            user=user,
            di=di,
        )
    assert http.json() == op_result.model_dump(mode="json")


async def test_hitl_conversation_send_rest_match_op(
    client: AsyncClient,
    di: FlowsDi,
    worktracker_di: object,
    unique_id: str,
    system_user_id: str,
) -> None:
    _ = worktracker_di
    parked = await park_hitl_session(
        di, unique_id, mode=HandoffMode.TAKEOVER, owner_user_id=system_user_id
    )
    text = f"оператор {unique_id}"
    key = f"cmd-{unique_id}"
    http = await client.post(
        f"{HITL_API}/{parked.work_item_id}/conversation/messages",
        json={"text": text, "idempotency_key": key},
    )
    assert http.status_code == 200, http.text
    with _system_scope(system_user_id) as user:
        op_result = await op_flows_hitl_conversation_send(
            OperatorMessageRequest(
                work_item_id=parked.work_item_id,
                text=text,
                idempotency_key=key,
            ),
            user=user,
            di=di,
        )
    assert http.json() == op_result.model_dump(mode="json")


async def test_hitl_conversation_get_missing_rest_match_op(
    client: AsyncClient,
    di: FlowsDi,
    system_user_id: str,
    unique_id: str,
) -> None:
    missing_id = f"wi-missing-{unique_id}"
    http = await client.get(f"{HITL_API}/{missing_id}/conversation")
    assert http.status_code == 404, http.text
    assert http.json()["error_code"] == "not_found"
    with _system_scope(system_user_id) as user:
        with pytest.raises(WsCommandError) as raised:
            await op_flows_hitl_conversation_get(
                HitlConversationWorkItemPayload(work_item_id=missing_id),
                user=user,
                di=di,
            )
    assert raised.value.code == "not_found"


async def test_hitl_conversation_send_forbidden_rest_match_op(
    client: AsyncClient,
    di: FlowsDi,
    worktracker_di: object,
    unique_id: str,
    system_user_id: str,
    auth_headers_system_user2: dict[str, str],
    system_user2_id: str,
) -> None:
    _ = worktracker_di
    parked = await park_hitl_session(
        di, unique_id, mode=HandoffMode.TAKEOVER, owner_user_id=system_user_id
    )
    http = await client.post(
        f"{HITL_API}/{parked.work_item_id}/conversation/messages",
        headers=auth_headers_system_user2,
        json={"text": "hi", "idempotency_key": f"k-{unique_id}"},
    )
    assert http.status_code == 403, http.text
    assert http.json()["error_code"] == "forbidden"
    with _system_scope(system_user2_id) as user:
        with pytest.raises(WsCommandError) as raised:
            await op_flows_hitl_conversation_send(
                OperatorMessageRequest(
                    work_item_id=parked.work_item_id,
                    text="hi",
                    idempotency_key=f"k-{unique_id}",
                ),
                user=user,
                di=di,
            )
    assert raised.value.code == "forbidden"
