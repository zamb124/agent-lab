"""Prod-like: company init enqueue — REST и `op_*` один handler."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

import pytest
from httpx import ASGITransport, AsyncClient

from apps.flows.di import FlowsDi
from apps.flows.realtime.company_operations import (
    CompanyInitPayload,
    op_flows_company_init,
)
from core.context import reset_context, set_context
from core.internal_context_headers import build_internal_context_headers
from core.models.context_models import Context
from core.models.identity_models import User
from core.utils.tokens import get_token_service
from core.websocket import WsCommandError
from tests.fixtures.ai_provider_defaults import make_test_company

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(60, func_only=True)]

PUBLIC = "/flows/api/v1/company/init"
INTERNAL = "/flows/api/v1/internal/company/init"


@contextmanager
def _company_scope(user_id: str, company_id: str, *, name: str) -> Generator[User]:
    user = User(user_id=user_id, name=name)
    token = set_context(
        Context(
            user=user,
            active_company=make_test_company(company_id=company_id, name=name),
            channel="api",
        )
    )
    try:
        yield user
    finally:
        reset_context(token)


def _scheduled_without_task_id(payload: dict[str, object]) -> dict[str, object]:
    task_id = payload["task_id"]
    if not isinstance(task_id, str) or task_id == "":
        raise AssertionError("company init: task_id обязателен")
    return {"status": payload["status"]}


async def test_company_init_public_http_equals_op(
    client: AsyncClient,
    di: FlowsDi,
    auth_token_company2: str,
    auth_headers_company2: dict[str, str],
) -> None:
    token_data = get_token_service().validate_token(auth_token_company2)
    body = {
        "company_id": token_data.company_id,
        "company_name": "Company Two",
        "subdomain": "company2",
    }
    http_response = await client.post(PUBLIC, json=body, headers=auth_headers_company2)
    assert http_response.status_code == 200, http_response.text
    http_payload = http_response.json()
    assert http_payload["status"] == "scheduled"

    with _company_scope(token_data.user_id, token_data.company_id, name="Company Two") as user:
        op_result = await op_flows_company_init(
            CompanyInitPayload.model_validate(body),
            user=user,
            di=di,
        )
    assert _scheduled_without_task_id(http_payload) == _scheduled_without_task_id(
        op_result.model_dump(mode="json")
    )


async def test_company_init_public_rejects_system(
    client: AsyncClient,
    di: FlowsDi,
    system_user_id: str,
) -> None:
    http_response = await client.post(
        PUBLIC,
        json={"company_id": "system", "company_name": "System", "subdomain": "system"},
    )
    assert http_response.status_code == 400, http_response.text
    assert http_response.json()["error_code"] == "ws_invalid_payload"

    with _company_scope(system_user_id, "system", name="System") as user:
        op_result = await op_flows_company_init(
            CompanyInitPayload(
                company_id="system",
                company_name="System",
                subdomain="system",
            ),
            user=user,
            di=di,
        )
    assert op_result.status == "scheduled"
    assert op_result.task_id


async def test_company_init_internal_system_http_equals_op(
    app: object,
    di: FlowsDi,
    system_user_id: str,
) -> None:
    headers = build_internal_context_headers(company_id="system", user_id=system_user_id)
    body = {
        "company_id": "system",
        "company_name": "System",
        "subdomain": "system",
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        http_response = await http_client.post(INTERNAL, json=body, headers=headers)
    assert http_response.status_code == 200, http_response.text
    http_payload = http_response.json()
    assert http_payload["status"] == "scheduled"

    with _company_scope(system_user_id, "system", name="System") as user:
        op_result = await op_flows_company_init(
            CompanyInitPayload.model_validate(body),
            user=user,
            di=di,
        )
    assert _scheduled_without_task_id(http_payload) == _scheduled_without_task_id(
        op_result.model_dump(mode="json")
    )


async def test_company_init_company_mismatch_is_forbidden(
    client: AsyncClient,
    di: FlowsDi,
    auth_token_company2: str,
    auth_headers_company2: dict[str, str],
    unique_id: str,
) -> None:
    token_data = get_token_service().validate_token(auth_token_company2)
    foreign_company_id = f"company-init-foreign-{unique_id}"
    body = {
        "company_id": foreign_company_id,
        "company_name": "Foreign",
        "subdomain": "foreign",
    }
    http_response = await client.post(PUBLIC, json=body, headers=auth_headers_company2)
    assert http_response.status_code == 403, http_response.text
    assert http_response.json()["error_code"] == "forbidden"

    with _company_scope(token_data.user_id, token_data.company_id, name="Company Two") as user:
        with pytest.raises(WsCommandError) as raised:
            await op_flows_company_init(
                CompanyInitPayload.model_validate(body),
                user=user,
                di=di,
            )
    assert raised.value.code == "forbidden"
