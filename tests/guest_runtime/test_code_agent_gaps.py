from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping

import pytest
from httpx import AsyncClient

from core.clients.guest_runtime_client import GuestRuntimeClient
from core.config import get_settings
from core.files.create_spec import FileCreateSpec
from core.guest_runtime.models import (
    CodeAgentSourceFile,
    GuestInvokeKind,
    GuestLanguage,
    GuestLeaseCapError,
)
from core.models.identity_models import Company, User
from core.tracing.models import Span
from core.utils.tokens import get_token_service
from tests.files.chunked_upload_helpers import code_agent_source_upload_spec_json
from tests.fixtures.ai_provider_defaults import make_test_company
from tests.fixtures.auth import set_test_company_member_roles
from tests.fixtures.s3 import require_s3_configured
from tests.guest_runtime.http_helpers import (
    FLOWS_FILES_PREFIX,
    code_agent_headers,
    code_agent_status_files,
    create_code_agent_flow,
    ensure_code_agent_catalog,
    example_echo_cli_bytes,
    guest_ensure_lease_request,
    rebuild_code_agent,
    upload_code_agent_file,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(300, func_only=True)]

_BUILD_OP = "guest_runtime.build_usage"
_SESSION_OP = "guest_runtime.session_usage"
_START_OP = "guest_runtime.start"


async def _seed_echo_node(
    flows_client: AsyncClient,
    headers: Mapping[str, str],
    *,
    flow_id: str,
    node_id: str,
    invoke_argv: list[str],
) -> tuple[str, list[CodeAgentSourceFile]]:
    await create_code_agent_flow(
        flows_client,
        headers,
        flow_id=flow_id,
        node_id=node_id,
        invoke_argv=invoke_argv,
    )
    catalog_id = await ensure_code_agent_catalog(
        flows_client, headers, flow_id=flow_id, node_id=node_id
    )
    await upload_code_agent_file(
        flows_client,
        headers,
        flow_id=flow_id,
        node_id=node_id,
        original_name="main.py",
        content=example_echo_cli_bytes(),
    )
    _ = await rebuild_code_agent(
        flows_client, headers, flow_id=flow_id, node_id=node_id, invoke_argv=invoke_argv
    )
    status_catalog_id, files = await code_agent_status_files(
        flows_client, headers, flow_id=flow_id, node_id=node_id
    )
    assert status_catalog_id == catalog_id
    return catalog_id, files


async def _wait_span_ops(
    frontend_di,
    flow_id: str,
    ops: set[str],
    *,
    timeout_seconds: float = 15.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        spans = await Span.list_by_flow_id(flow_id, limit=100)
        names = {span.operation_name for span in spans}
        if ops <= names:
            return
        await asyncio.sleep(0.2)
    spans = await Span.list_by_flow_id(flow_id, limit=100)
    names = {span.operation_name for span in spans}
    raise AssertionError(f"missing span ops {sorted(ops - names)} in {sorted(names)}")


async def test_code_agent_upload_over_source_cap_is_400(
    flows_client_http: AsyncClient,
    office_service: object,
    guest_runtime_service: object,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    _ = office_service, guest_runtime_service
    require_s3_configured()
    headers = code_agent_headers(auth_headers_system)
    flow_id = f"ca_cap_{unique_id}"
    node_id = "agent"
    await create_code_agent_flow(
        flows_client_http,
        headers,
        flow_id=flow_id,
        node_id=node_id,
        invoke_argv=["python3", "main.py"],
    )
    _ = await ensure_code_agent_catalog(
        flows_client_http, headers, flow_id=flow_id, node_id=node_id
    )
    max_bytes = get_settings().guest_runtime.max_source_bytes
    spec = FileCreateSpec.model_validate_json(
        code_agent_source_upload_spec_json(flow_id=flow_id, node_id=node_id)
    )
    response = await flows_client_http.post(
        f"{FLOWS_FILES_PREFIX}/uploads",
        headers=headers,
        json={
            "spec": spec.model_dump(mode="json"),
            "original_name": "huge.bin",
            "content_type": "application/octet-stream",
            "file_size": max_bytes + 1,
        },
    )
    assert response.status_code == 400, response.text
    assert "exceeds" in response.text


@pytest.mark.timeout(600, func_only=True)
async def test_code_agent_rebuild_and_drop_write_billing_spans(
    flows_client_http: AsyncClient,
    office_service: object,
    guest_runtime_service: object,
    frontend_di,
    auth_headers_system: dict[str, str],
    system_user_id: str,
    unique_id: str,
) -> None:
    _ = office_service, guest_runtime_service
    require_s3_configured()
    headers = code_agent_headers(auth_headers_system)
    flow_id = f"ca_billspan_{unique_id}"
    node_id = "agent"
    invoke_argv = ["python3", "main.py"]
    catalog_id, files = await _seed_echo_node(
        flows_client_http,
        headers,
        flow_id=flow_id,
        node_id=node_id,
        invoke_argv=invoke_argv,
    )
    await _wait_span_ops(frontend_di, flow_id, {_BUILD_OP})
    digest_again = await rebuild_code_agent(
        flows_client_http,
        headers,
        flow_id=flow_id,
        node_id=node_id,
        invoke_argv=invoke_argv,
    )
    _ = digest_again
    spans_after_skip = await Span.list_by_flow_id(
        flow_id, limit=100
    )
    build_count = sum(1 for span in spans_after_skip if span.operation_name == _BUILD_OP)
    assert build_count == 1
    body = guest_ensure_lease_request(
        flow_id=flow_id,
        node_id=node_id,
        company_id="system",
        user_id=system_user_id,
        catalog_id=catalog_id,
        files=files,
        unique_id=unique_id,
        invoke_argv=invoke_argv,
        language=GuestLanguage.PYTHON,
        invoke_kind=GuestInvokeKind.CLI,
    )
    farm = GuestRuntimeClient()
    _ = await farm.ensure_lease(body)
    await farm.drop(flow_id, node_id)
    await _wait_span_ops(frontend_di, flow_id, {_BUILD_OP, _START_OP, _SESSION_OP})


@pytest.mark.timeout(600, func_only=True)
async def test_code_agent_idle_reaper_bills_session(
    flows_client_http: AsyncClient,
    office_service: object,
    guest_runtime_service: object,
    frontend_di,
    auth_headers_system: dict[str, str],
    system_user_id: str,
    unique_id: str,
) -> None:
    _ = office_service, guest_runtime_service
    require_s3_configured()
    headers = code_agent_headers(auth_headers_system)
    flow_id = f"ca_reap_{unique_id}"
    node_id = "agent"
    invoke_argv = ["python3", "main.py"]
    catalog_id, files = await _seed_echo_node(
        flows_client_http,
        headers,
        flow_id=flow_id,
        node_id=node_id,
        invoke_argv=invoke_argv,
    )
    body = guest_ensure_lease_request(
        flow_id=flow_id,
        node_id=node_id,
        company_id="system",
        user_id=system_user_id,
        catalog_id=catalog_id,
        files=files,
        unique_id=unique_id,
        invoke_argv=invoke_argv,
        language=GuestLanguage.PYTHON,
        invoke_kind=GuestInvokeKind.CLI,
        idle_ttl_seconds=1,
    )
    farm = GuestRuntimeClient()
    _ = await farm.ensure_lease(body)
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        status = await farm.status(flow_id, node_id)
        if status.lease is None:
            break
        await asyncio.sleep(0.5)
    else:
        raise AssertionError("idle reaper did not drop the lease")
    await _wait_span_ops(frontend_di, flow_id, {_SESSION_OP})


@pytest.mark.timeout(600, func_only=True)
async def test_code_agent_third_lease_http_409(
    flows_client_http: AsyncClient,
    office_service: object,
    guest_runtime_service: object,
    frontend_di,
    unique_id: str,
) -> None:
    _ = office_service, guest_runtime_service
    require_s3_configured()
    company_id = f"co_guest_cap_{unique_id}"
    user_id = f"u_guest_cap_{unique_id}"
    company = make_test_company(
        company_id=company_id,
        name="Guest cap",
        owner_user_id=user_id,
        members={user_id: ["owner", "admin"]},
        subdomain=f"gc{unique_id[:12]}",
        balance=5000.0,
    )
    user = User(
        user_id=user_id,
        name="Guest Cap",
        emails=[f"{user_id}@test.com"],
        companies={company_id: ["owner", "admin"]},
        active_company_id=company_id,
        groups=["admin"],
    )
    await Company.set(company)
    await User.set(user)
    await set_test_company_member_roles(
        frontend_di.authz_service,
        company_id=company_id,
        user_id=user_id,
        roles=["owner", "admin"],
    )
    token = get_token_service().create_token(user_id, company_id=company_id)
    headers = code_agent_headers({"Authorization": f"Bearer {token}"})
    invoke_argv = ["python3", "main.py"]
    catalog_id, files = await _seed_echo_node(
        flows_client_http,
        headers,
        flow_id=f"ca_cap_seed_{unique_id}",
        node_id="agent",
        invoke_argv=invoke_argv,
    )
    cap = get_settings().guest_runtime.max_leases_per_company
    farm = GuestRuntimeClient()
    held: list[tuple[str, str]] = []
    try:
        for index in range(cap):
            flow_id = f"ca_cap{index}_{unique_id}"
            node_id = "agent"
            body = guest_ensure_lease_request(
                flow_id=flow_id,
                node_id=node_id,
                company_id=company_id,
                user_id=user_id,
                catalog_id=catalog_id,
                files=files,
                unique_id=f"{unique_id}{index}",
                invoke_argv=invoke_argv,
                language=GuestLanguage.PYTHON,
                invoke_kind=GuestInvokeKind.CLI,
            )
            _ = await farm.ensure_lease(body)
            held.append((flow_id, node_id))
        overflow_flow_id = f"ca_cap_over_{unique_id}"
        overflow_body = guest_ensure_lease_request(
            flow_id=overflow_flow_id,
            node_id="agent",
            company_id=company_id,
            user_id=user_id,
            catalog_id=catalog_id,
            files=files,
            unique_id=f"{unique_id}over",
            invoke_argv=invoke_argv,
            language=GuestLanguage.PYTHON,
            invoke_kind=GuestInvokeKind.CLI,
        )
        with pytest.raises(GuestLeaseCapError, match="cap"):
            await farm.ensure_lease(overflow_body)
    finally:
        for flow_id, node_id in held:
            await farm.drop(flow_id, node_id)
