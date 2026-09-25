"""Prod-like: Lara pending-actions apply — REST и `op_*` один handler."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

import pytest
from httpx import AsyncClient

from apps.crm.di import CrmDi
from apps.flows.di import FlowsDi
from apps.flows.realtime.lara_operations import (
    LaraPendingActionApplyPayload,
    op_flows_lara_pending_actions_apply,
)
from apps.flows.src.services.lara_action_engine import LaraPendingAction
from core.context import reset_context, set_context
from core.models.context_models import Context
from core.models.identity_models import User
from core.websocket import WsCommandError
from tests.fixtures.ai_provider_defaults import make_test_company

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(60, func_only=True)]

APPLY = "/flows/api/v1/lara/pending-actions/apply"


class _LaraContext:
    def __init__(self, context_id: str) -> None:
        self.context_id = context_id


@contextmanager
def _user_scope(user_id: str, *, name: str) -> Generator[User]:
    user = User(user_id=user_id, name=name)
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


def _apply_payload(*, pending_action_id: str, context_id: str) -> LaraPendingActionApplyPayload:
    return LaraPendingActionApplyPayload(
        pending_action_id=pending_action_id,
        context_id=context_id,
        idempotency_key=None,
    )


async def test_lara_pending_actions_apply_http_equals_op_after_crm_propose(
    client: AsyncClient,
    di: FlowsDi,
    crm_service: object,
    crm_client: AsyncClient,
    crm_di,
    system_user_id: str,
    unique_id: str,
) -> None:
    _ = crm_service, crm_client
    if not isinstance(crm_di, CrmDi):
        raise TypeError("crm_di fixture must be CrmDi")
    context_id = f"ctx-lara-apply-{unique_id}"
    namespace = f"g_{unique_id}"
    with _user_scope(system_user_id, name="System"):
        proposed = await di.lara_facade.preview_crm_create_note(
            name=f"lara-cmd-note-{unique_id}",
            description="identity: HTTP apply == op apply",
            note_date=None,
            namespace=namespace,
            state=_LaraContext(context_id),
            idempotency_key=f"{unique_id}-preview",
        )

    body = {
        "pending_action_id": proposed.pending_action_id,
        "context_id": context_id,
    }
    http_response = await client.post(APPLY, json=body)
    assert http_response.status_code == 200, http_response.text
    http_payload = http_response.json()
    assert http_payload["status"] == "applied"
    assert http_payload["pending_action_id"] == proposed.pending_action_id

    result_payload = http_payload["result"]
    if not isinstance(result_payload, dict):
        raise AssertionError("Lara apply: result должен быть объектом")
    entity_payload = result_payload["entity"]
    if not isinstance(entity_payload, dict):
        raise AssertionError("Lara apply: result.entity должен быть CRM-сущностью")
    entity_id = entity_payload["entity_id"]
    if not isinstance(entity_id, str) or entity_id == "":
        raise AssertionError("Lara apply: CRM entity_id обязателен")
    note = await crm_di.entity_service.get_entity(entity_id)
    if note is None:
        raise AssertionError(f"Lara apply: CRM-заметка {entity_id} не найдена")
    assert note.name == f"lara-cmd-note-{unique_id}"

    with _user_scope(system_user_id, name="System") as user:
        op_result = await op_flows_lara_pending_actions_apply(
            _apply_payload(
                pending_action_id=proposed.pending_action_id,
                context_id=context_id,
            ),
            user=user,
            di=di,
        )

    assert isinstance(op_result, LaraPendingAction)
    assert http_payload == op_result.model_dump(mode="json")
    assert op_result.status == "applied"
    assert op_result.result == result_payload


async def test_lara_pending_actions_apply_owner_mismatch_is_forbidden(
    client: AsyncClient,
    di: FlowsDi,
    system_user_id: str,
    unique_id: str,
) -> None:
    context_id = f"ctx-lara-owner-{unique_id}"
    foreign_user_id = f"user-lara-foreign-{unique_id}"
    with _user_scope(foreign_user_id, name="Foreign"):
        proposed = await di.lara_facade.preview_crm_create_note(
            name=f"lara-owner-note-{unique_id}",
            description="identity: чужой pending_action_id",
            note_date=None,
            namespace=f"g_{unique_id}",
            state=_LaraContext(context_id),
            idempotency_key=f"{unique_id}-owner-preview",
        )

    body = {
        "pending_action_id": proposed.pending_action_id,
        "context_id": context_id,
    }
    http_response = await client.post(APPLY, json=body)
    assert http_response.status_code == 403, http_response.text
    assert http_response.json()["error_code"] == "forbidden"

    with _user_scope(system_user_id, name="System") as user:
        with pytest.raises(WsCommandError) as raised:
            await op_flows_lara_pending_actions_apply(
                _apply_payload(
                    pending_action_id=proposed.pending_action_id,
                    context_id=context_id,
                ),
                user=user,
                di=di,
            )
    assert raised.value.code == "forbidden"


async def test_lara_pending_actions_apply_missing_is_invalid(
    client: AsyncClient,
    di: FlowsDi,
    system_user_id: str,
    unique_id: str,
) -> None:
    missing_id = f"pending-missing-{unique_id}"
    context_id = f"ctx-lara-missing-{unique_id}"
    http_response = await client.post(
        APPLY,
        json={"pending_action_id": missing_id, "context_id": context_id},
    )
    assert http_response.status_code == 400, http_response.text
    assert http_response.json()["error_code"] == "ws_invalid_payload"

    with _user_scope(system_user_id, name="System") as user:
        with pytest.raises(WsCommandError) as raised:
            await op_flows_lara_pending_actions_apply(
                _apply_payload(pending_action_id=missing_id, context_id=context_id),
                user=user,
                di=di,
            )
    assert raised.value.code == "ws_invalid_payload"
