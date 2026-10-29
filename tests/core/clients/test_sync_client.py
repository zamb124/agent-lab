"""SyncClient against real Sync HTTP service."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import cast

import pytest
from httpx2 import AsyncClient

from core.clients.service_client import ServiceClientError
from core.clients.sync_client import SyncClient
from core.context import clear_context, get_context, set_context
from core.context.job_context import build_job_context
from core.identity.flow_employee import ensure_flow_employee, flow_employee_user_id
from core.models.identity_models import Company, User
from tests.fixtures.ai_provider_defaults import make_test_company
from tests.sync.api._helpers import seed_namespace_via_repo

pytestmark = pytest.mark.asyncio

_SYNC_BASE = "http://127.0.0.1:9005"


@contextmanager
def _employee_context(*, user: User, company: Company) -> Iterator[None]:
    previous = get_context()
    employee_ctx = build_job_context(
        company=company,
        user=user,
        host="",
        trace_id="sync-client-test",
        session_id="s",
        channel="a2a",
    )
    set_context(employee_ctx)
    try:
        yield
    finally:
        if previous is None:
            clear_context()
        else:
            set_context(previous)


async def test_sync_client_list_channels_send_and_list_messages(
    flows_service: object,
    sync_service: object,
    frontend_di: object,
    auth_token_system: str,
    unique_id: str,
) -> None:
    _ = flows_service, sync_service
    flow_id = f"syncclient_{unique_id}"
    company = cast(Company | None, await Company.get("system"))
    assert company is not None
    employee = await ensure_flow_employee(
        frontend_di.authz_service,
        flow_id=flow_id,
        company_id="system",
        name="Sync Client Worker",
        roles=["member"],
        curator_user_ids=["system"],
    )
    emp_id = flow_employee_user_id(flow_id)
    assert emp_id == employee.user_id
    namespace = f"ns_{unique_id}_sc"
    _ = await seed_namespace_via_repo(frontend_di, "system", namespace)
    headers = {"Authorization": f"Bearer {auth_token_system}"}

    async with AsyncClient(base_url=_SYNC_BASE, timeout=60.0) as http:
        cr = await http.post(
            "/sync/api/v1/channels/",
            headers=headers,
            json={
                "namespace": namespace,
                "type": "topic",
                "name": "sc_ch",
                "is_private": False,
            },
        )
        assert cr.status_code == 201, cr.text
        channel_id_raw = cr.json()["channel_id"]
        assert isinstance(channel_id_raw, str) and channel_id_raw.strip()
        channel_id = channel_id_raw
        mr = await http.post(
            f"/sync/api/v1/channels/{channel_id}/members",
            headers=headers,
            json={"user_id": emp_id, "role": "member"},
        )
        assert mr.status_code in (200, 201), mr.text

    with _employee_context(user=employee, company=company):
        client = SyncClient()
        channels = await client.list_channels(namespace=namespace, limit=50, offset=0)
        items = channels.get("items")
        assert isinstance(items, list)
        assert any(
            item.get("channel_id") == channel_id for item in items if isinstance(item, dict)
        )

        sent = await client.send_message(
            channel_id, text=f"hello from sync client {unique_id}"
        )
        assert sent["channel_id"] == channel_id
        message_id = sent.get("message_id")
        assert isinstance(message_id, str) and message_id.strip()

        listed = await client.list_messages(channel_id, limit=20)
        assert listed["channel_id"] == channel_id
        count = listed.get("count")
        assert isinstance(count, int) and count >= 1

        threads = await client.list_threads(channel_id, limit=50, offset=0)
        assert threads["channel_id"] == channel_id
        assert isinstance(threads.get("items"), list)


async def test_sync_client_send_non_member_denied(
    flows_service: object,
    sync_service: object,
    auth_token_system: str,
    unique_id: str, frontend_di,
) -> None:
    _ = flows_service, sync_service
    emp_id = f"flow_employee_denied_sc_{unique_id}"
    namespace = f"ns_{unique_id}_scdn"
    _ = await seed_namespace_via_repo(frontend_di, "system", namespace)
    headers = {"Authorization": f"Bearer {auth_token_system}"}

    async with AsyncClient(base_url=_SYNC_BASE, timeout=60.0) as http:
        cr = await http.post(
            "/sync/api/v1/channels/",
            headers=headers,
            json={
                "namespace": namespace,
                "type": "topic",
                "name": "dn_ch",
                "is_private": True,
            },
        )
        assert cr.status_code == 201, cr.text
        channel_id_raw = cr.json()["channel_id"]
        assert isinstance(channel_id_raw, str) and channel_id_raw.strip()
        channel_id = channel_id_raw

    company = make_test_company(company_id="system", name="System")
    outsider = User(
        user_id=emp_id,
        name="Denied Worker",
        companies={"system": ["member"]},
        active_company_id="system",
    )
    with _employee_context(user=outsider, company=company):
        with pytest.raises(ServiceClientError):
            _ = await SyncClient().send_message(channel_id, text="should be denied")
