from __future__ import annotations

import hashlib
import time
from pathlib import Path

import pytest
from httpx import AsyncClient

from apps.guest_runtime.services.farm_service import GuestFarmService
from apps.guest_runtime.services.identity import guest_identity_scope
from apps.guest_runtime.services.lease_store import GuestLeaseStore
from apps.guest_runtime.services.slots import (
    build_docker_image,
    docker_image_inspect,
    maybe_delete_docker_image,
    require_docker,
    start_docker_slot,
    stop_slot,
)
from core.capabilities.models import CapabilityExecutionContext
from core.capabilities.tokens import (
    CapabilityExecutionTokenClaims,
    issue_execution_token,
)
from core.clients.files_client import FilesClient
from core.config.models import GuestRuntimeFarmConfig
from core.guest_runtime.models import (
    GuestExecutorKind,
    GuestInvokeKind,
    GuestLanguage,
    GuestRebuildRequest,
)
from core.http import get_httpx_client
from core.models.identity_models import Company, User
from core.types import JsonObject
from tests.fixtures.s3 import require_s3_configured
from tests.guest_runtime.http_helpers import (
    code_agent_headers,
    code_agent_status_files,
    create_code_agent_flow,
    ensure_code_agent_catalog,
    example_cli_node_bytes,
    example_main_py_bytes,
    guest_ensure_lease_request,
    upload_code_agent_file,
)


async def require_docker_configured() -> None:
    try:
        await require_docker()
    except RuntimeError as exc:
        pytest.skip(str(exc))


def _guest_execution_token(
    *,
    flow_id: str,
    user_id: str,
    test_scope: str,
    session_id: str,
    task_id: str,
    context_id: str,
    channel: str,
    request_id: str,
    source_node_id: str,
    namespace: str | None,
) -> str:
    return issue_execution_token(
        CapabilityExecutionTokenClaims(
            company_id="system",
            user_id=user_id,
            flow_id=flow_id,
            branch_id="default",
            session_id=session_id,
            task_id=task_id,
            context_id=context_id,
            channel=channel,
            request_id=request_id,
            source_node_id=source_node_id,
            namespace=namespace,
            test_scope=test_scope,
            allowed_capabilities=["text.summarize"],
            max_calls=8,
            exp=int(time.time()) + 3600,
        )
    )


def _docker_slot_env(*, flow_id: str, execution_token: str, capability_context: str) -> dict[str, str]:
    return {
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "OPENAI_BASE_URL": "http://host.docker.internal:9001/flows/api/v1/agent/llm/v1",
        "OPENAI_API_KEY": execution_token,
        "CAPABILITY_GATEWAY_URL": "http://host.docker.internal:9016",
        "PLATFORM_EXECUTION_TOKEN": execution_token,
        "PLATFORM_CAPABILITY_CONTEXT": capability_context,
        "PLATFORM_SESSION_ID": "sess",
        "PLATFORM_TASK_ID": "task",
        "PLATFORM_FLOW_ID": flow_id,
        "PLATFORM_REQUEST_ID": "req",
        "PLATFORM_TRACE_ID": "tr",
        "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


async def _invoke_shim_cli(
    shim_url: str,
    *,
    flow_id: str,
    invoke_argv: list[str],
    text: str,
) -> JsonObject:
    async with get_httpx_client(timeout=30.0) as client:
        context = await client.post(
            f"{shim_url}/context",
            json={
                "invoke_kind": "cli",
                "invoke_argv": invoke_argv,
                "request_id": "req",
                "trace_id": "tr",
                "session_id": "sess",
                "task_id": "task",
                "flow_id": flow_id,
                "guest_runtime_id": "rt",
                "guest_lease_id": "lease",
                "env": {},
            },
        )
        assert context.status_code == 200, context.text
        invoked = await client.post(f"{shim_url}/invoke", json={"text": text})
        assert invoked.status_code == 200, invoked.text
        payload = invoked.json()
        if not isinstance(payload, dict):
            raise AssertionError(f"shim invoke must return object: {payload!r}")
        return payload


@pytest.mark.asyncio
@pytest.mark.timeout(300, func_only=True)
async def test_docker_build_and_cli_invoke(
    tmp_path: Path,
    unique_id: str,
    system_user_id: str,
    platform_test_scope: str,
    mock_llm_redis,
) -> None:
    await require_docker_configured()
    await mock_llm_redis(
        [
            {"type": "text", "content": "docker-llm"},
            {"type": "text", "content": "docker-summary"},
        ]
    )
    flow_id = f"ca_dock_{unique_id}"
    source_digest_hex = hashlib.sha256(f"{flow_id}-py".encode()).hexdigest()
    image_digest, image_bytes = await build_docker_image(
        language=GuestLanguage.PYTHON,
        contents={"main.py": example_main_py_bytes()},
        data_dir=tmp_path,
        flow_id=flow_id,
        node_id="agent",
        source_digest_hex=source_digest_hex,
    )
    assert image_bytes > 0
    execution_token = _guest_execution_token(
        flow_id=flow_id,
        user_id=system_user_id,
        test_scope=platform_test_scope,
        session_id="sess",
        task_id="task",
        context_id="ctx",
        channel="a2a",
        request_id="req",
        source_node_id="agent",
        namespace="default",
    )
    capability_context = CapabilityExecutionContext(
        execution_token=execution_token,
        company_id="system",
        user_id=system_user_id,
        flow_id=flow_id,
        branch_id="default",
        session_id="sess",
        task_id="task",
        context_id="ctx",
        channel="a2a",
        request_id="req",
        trace_id="tr",
        source_node_id="agent",
        namespace="default",
    ).model_dump_json()
    farm = GuestRuntimeFarmConfig(executor="docker", data_dir=str(tmp_path))
    slot = await start_docker_slot(
        farm=farm,
        image_digest=image_digest,
        env=_docker_slot_env(
            flow_id=flow_id,
            execution_token=execution_token,
            capability_context=capability_context,
        ),
        extra_host_pairs=[],
    )
    try:
        payload = await _invoke_shim_cli(
            slot.shim_url,
            flow_id=flow_id,
            invoke_argv=["python3", "main.py"],
            text="hello-docker",
        )
        assert payload["text"] == "hello-docker"
    finally:
        await stop_slot(slot)
        await maybe_delete_docker_image(image_digest, GuestExecutorKind.DOCKER)


@pytest.mark.asyncio
@pytest.mark.timeout(300, func_only=True)
async def test_docker_build_and_node_cli_invoke(tmp_path: Path, unique_id: str) -> None:
    await require_docker_configured()
    flow_id = f"ca_dockn_{unique_id}"
    source_digest_hex = hashlib.sha256(f"{flow_id}-node".encode()).hexdigest()
    image_digest, image_bytes = await build_docker_image(
        language=GuestLanguage.NODE,
        contents={"main.js": example_cli_node_bytes()},
        data_dir=tmp_path,
        flow_id=flow_id,
        node_id="agent",
        source_digest_hex=source_digest_hex,
    )
    assert image_bytes > 0
    farm = GuestRuntimeFarmConfig(executor="docker", data_dir=str(tmp_path))
    slot = await start_docker_slot(
        farm=farm,
        image_digest=image_digest,
        env=_docker_slot_env(
            flow_id=flow_id,
            execution_token="docker-test-token",
            capability_context="{}",
        ),
        extra_host_pairs=[],
    )
    try:
        payload = await _invoke_shim_cli(
            slot.shim_url,
            flow_id=flow_id,
            invoke_argv=["node", "main.js"],
            text="hello-node-docker",
        )
        assert payload["text"] == "hello-node-docker"
    finally:
        await stop_slot(slot)
        await maybe_delete_docker_image(image_digest, GuestExecutorKind.DOCKER)


@pytest.mark.asyncio
@pytest.mark.timeout(300, func_only=True)
async def test_docker_farm_rebuild_and_ensure_lease(
    flows_client_http: AsyncClient,
    office_service: object,
    guest_runtime_service: object,
    guest_runtime_di,
    guest_farm_service: tuple[GuestFarmService, list[tuple[str, str]]],
    auth_headers_system: dict[str, str],
    system_user_id: str,
    unique_id: str,
    tmp_path: Path,
    platform_test_scope: str,
    mock_llm_redis,
) -> None:
    _ = office_service, guest_runtime_service
    await require_docker_configured()
    require_s3_configured()
    await mock_llm_redis(
        [
            {"type": "text", "content": "docker-llm"},
            {"type": "text", "content": "docker-summary"},
        ]
    )
    _, held = guest_farm_service
    headers = code_agent_headers(auth_headers_system)
    flow_id = f"ca_dfarm_{unique_id}"
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
    docker_farm = GuestFarmService(
        lease_store=GuestLeaseStore(
            guest_runtime_di.redis_client,
            guest_runtime_di.farm_service.farm_config,
        ),
        files_client=FilesClient(service="office"),
        farm=GuestRuntimeFarmConfig(executor="docker", data_dir=str(tmp_path)),
    )
    held.append((flow_id, node_id))
    async with guest_identity_scope(user=user, company=company):
        rebuilt = await docker_farm.rebuild(
            GuestRebuildRequest(
                flow_id=flow_id,
                node_id=node_id,
                company_id=company.company_id,
                user_id=user.user_id,
                catalog_id=catalog_id,
                language=GuestLanguage.PYTHON,
                invoke_kind=GuestInvokeKind.CLI,
                invoke_argv=invoke_argv,
                files=files,
            )
        )
        assert rebuilt.image_digest.startswith("sha256:")
        inspected = await docker_image_inspect(rebuilt.image_digest)
        if inspected is None:
            raise RuntimeError(f"docker inspect failed for {rebuilt.image_digest}")
        inspect_id, inspect_bytes = inspected
        assert inspect_id == rebuilt.image_digest
        assert inspect_bytes == rebuilt.image_bytes
        lease = await docker_farm.ensure_lease(
            guest_ensure_lease_request(
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
                execution_token=_guest_execution_token(
                    flow_id=flow_id,
                    user_id=user.user_id,
                    test_scope=platform_test_scope,
                    session_id=f"sess-{unique_id}",
                    task_id=f"task-{unique_id}",
                    context_id=f"ctx-{unique_id}",
                    channel="web",
                    request_id=f"req-{unique_id}",
                    source_node_id=node_id,
                    namespace=None,
                ),
            )
        )
        rpc: JsonObject = {
            "jsonrpc": "2.0",
            "id": "1",
            "method": "SendMessage",
            "params": {"message": {"parts": [{"text": "hello-docker-farm"}]}},
        }
        invoked = await docker_farm.invoke_a2a(flow_id, node_id, rpc)
        result = invoked.get("result")
        if not isinstance(result, dict):
            raise AssertionError(f"farm invoke missing result: {invoked}")
        status = result.get("status")
        if not isinstance(status, dict):
            raise AssertionError(f"farm invoke missing status: {result}")
        assert status.get("state") == "TASK_STATE_COMPLETED"
        assert lease.image_digest == rebuilt.image_digest
        await docker_farm.drop_runtime(flow_id, node_id)
