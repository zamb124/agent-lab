from __future__ import annotations

import pytest
from httpx2 import AsyncClient

from apps.guest_runtime.services.farm_service import GuestFarmService
from apps.guest_runtime.services.identity import guest_identity_scope
from core.guest_runtime.models import GuestInvokeKind, GuestLanguage
from core.models.identity_models import Company, User
from tests.fixtures.s3 import require_s3_configured
from tests.guest_runtime.http_helpers import (
    code_agent_headers,
    code_agent_status_files,
    create_code_agent_flow,
    ensure_code_agent_catalog,
    example_main_py_bytes,
    guest_ensure_lease_request,
    rebuild_code_agent,
    upload_code_agent_file,
)


@pytest.mark.asyncio
@pytest.mark.timeout(120, func_only=True)
async def test_lease_recreate_when_slots_empty(
    flows_client_http: AsyncClient,
    office_service: object,
    guest_runtime_service: object,
    guest_farm_service: tuple[GuestFarmService, list[tuple[str, str]]],
    auth_headers_system: dict[str, str],
    system_user_id: str,
    unique_id: str,
) -> None:
    _ = office_service, guest_runtime_service
    require_s3_configured()
    farm, held = guest_farm_service
    headers = code_agent_headers(auth_headers_system)
    flow_id = f"ca_recreate_{unique_id}"
    node_id = "agent"
    invoke_argv = ["python3", "main.py"]
    await create_code_agent_flow(
        flows_client_http,
        headers,
        flow_id=flow_id,
        node_id=node_id,
        invoke_argv=invoke_argv,
    )
    catalog_id = await ensure_code_agent_catalog(
        flows_client_http, headers, flow_id=flow_id, node_id=node_id
    )
    await upload_code_agent_file(
        flows_client_http,
        headers,
        flow_id=flow_id,
        node_id=node_id,
        original_name="main.py",
        content=example_main_py_bytes(),
    )
    digest = await rebuild_code_agent(
        flows_client_http,
        headers,
        flow_id=flow_id,
        node_id=node_id,
        invoke_argv=invoke_argv,
    )
    status_catalog_id, files = await code_agent_status_files(
        flows_client_http, headers, flow_id=flow_id, node_id=node_id
    )
    assert status_catalog_id == catalog_id
    user = await User.get(system_user_id)
    company = await Company.get("system")
    if user is None:
        raise RuntimeError("system user required")
    if company is None:
        raise RuntimeError("system company required")
    body = guest_ensure_lease_request(
        flow_id=flow_id,
        node_id=node_id,
        company_id=company.company_id,
        user_id=user.user_id,
        catalog_id=catalog_id,
        files=files,
        unique_id=unique_id,
        invoke_argv=invoke_argv,
        language=GuestLanguage.PYTHON,
        invoke_kind=GuestInvokeKind.CLI,
    )
    held.append((flow_id, node_id))
    async with guest_identity_scope(user=user, company=company):
        first = await farm.ensure_lease(body)
        assert first.image_digest == digest
        farm._slots.clear()
        second = await farm.ensure_lease(body)
    assert second.guest_lease_id == first.guest_lease_id
    assert second.image_digest == first.image_digest
