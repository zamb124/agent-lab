from __future__ import annotations

import shutil
import socket
from collections.abc import Awaitable, Callable, Sequence

import pytest
from httpx2 import AsyncClient

from apps.guest_runtime.services.slots import require_docker
from core.clients.a2a_client import A2AClient
from core.clients.flow_ui_client import FlowUIClient, FlowUIClientError
from core.clients.guest_runtime_client import GuestRuntimeClient
from core.clients.service_client import ServiceClientError
from core.config import get_settings
from core.guest_runtime.models import GuestInvokeKind, GuestLanguage
from core.models.identity_models import Company, User
from core.utils.tokens import get_token_service
from tests.fixtures.ai_provider_defaults import make_test_company
from tests.fixtures.auth import set_test_company_member_roles
from tests.fixtures.s3 import require_s3_configured
from tests.guest_runtime.http_helpers import (
    code_agent_headers,
    code_agent_logs,
    code_agent_status_files,
    ensure_code_agent_catalog,
    example_a2a_python_bytes,
    example_cli_node_bytes,
    example_echo_cli_bytes,
    example_effects_cli_bytes,
    example_fail_cli_bytes,
    example_interrupt_cli_bytes,
    example_llm_cli_bytes,
    example_main_py_bytes,
    guest_ensure_lease_request,
    rebuild_code_agent,
    upload_code_agent_file,
)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.real_taskiq,
    pytest.mark.timeout(180, func_only=True),
]

MockLlmQueue = Callable[[Sequence[object]], Awaitable[None]]

FLOWS_BASE_URL = "http://localhost:9001/flows"

INTERFACE = {
    "start_page_id": "main",
    "pages": [
        {
            "page_id": "main",
            "title": "Code agent",
            "blocks": [
                {"type": "conversation", "block_id": "conversation"},
            ],
        }
    ],
}

ECHO_CODE = (
    "async def run(args, state):\n"
    "    content = state.get('content')\n"
    "    if not isinstance(content, str):\n"
    "        raise ValueError('content required')\n"
    "    state['response'] = f\"ECHO:{content}\"\n"
    "    return state\n"
)

MERGE_CODE = (
    "async def run(args, state):\n"
    "    content = state.get('content')\n"
    "    response = state.get('response')\n"
    "    if not isinstance(content, str):\n"
    "        raise ValueError('content required')\n"
    "    if not isinstance(response, str):\n"
    "        raise ValueError('response required')\n"
    '    merged = f"{content}|{response}"\n'
    "    state['merged'] = merged\n"
    "    state['response'] = merged\n"
    "    return state\n"
)


def _require_node_binary() -> None:
    path = shutil.which("node")
    if path is None or path.strip() == "":
        raise RuntimeError("node binary is required for code_agent node e2e")


def _unused_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    if not isinstance(port, int) or port < 1:
        raise RuntimeError("failed to allocate listen port")
    return port


async def _seed_source(
    flows_client_http: AsyncClient,
    headers: dict[str, str],
    *,
    flow_id: str,
    node_id: str,
    original_name: str,
    content: bytes,
    invoke_argv: list[str],
    language: str = "python",
    invoke_kind: str = "cli",
    invoke_listen_port: int | None = None,
) -> str:
    catalog_id = await ensure_code_agent_catalog(
        flows_client_http, headers, flow_id=flow_id, node_id=node_id
    )
    _ = await upload_code_agent_file(
        flows_client_http,
        headers,
        flow_id=flow_id,
        node_id=node_id,
        original_name=original_name,
        content=content,
    )
    digest = await rebuild_code_agent(
        flows_client_http,
        headers,
        flow_id=flow_id,
        node_id=node_id,
        invoke_argv=invoke_argv,
        language=language,
        invoke_kind=invoke_kind,
        invoke_listen_port=invoke_listen_port,
    )
    assert digest.startswith("inprocess:")
    _ = catalog_id
    return digest


async def _seed_agent(
    flows_client_http: AsyncClient,
    headers: dict[str, str],
    *,
    flow_id: str,
    node_id: str,
) -> str:
    return await _seed_source(
        flows_client_http,
        headers,
        flow_id=flow_id,
        node_id=node_id,
        original_name="main.py",
        content=example_main_py_bytes(),
        invoke_argv=["python3", "main.py"],
    )


async def _send_expect_invoke_failure(sdk: FlowUIClient, prompt: str) -> None:
    try:
        turn = await sdk.send(prompt)
    except FlowUIClientError:
        return
    if turn.status != "failed":
        raise AssertionError(f"expected failed FlowUI turn, got {turn.status}")


@pytest.mark.asyncio
async def test_code_agent_example_flow_ui_client(
    flows_client_http: AsyncClient,
    office_service,
    guest_runtime_service,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    _ = office_service, guest_runtime_service
    require_s3_configured()
    headers = code_agent_headers(auth_headers_system)
    flow_id = f"ca_ex_{unique_id}"
    node_id = "agent"
    invoke_argv = ["python3", "main.py"]
    create = await flows_client_http.post(
        "/flows/api/v1/flows/",
        headers=headers,
        json={
            "flow_id": flow_id,
            "name": flow_id,
            "entry": node_id,
            "nodes": {
                node_id: {
                    "type": "code_agent",
                    "language": "python",
                    "invoke_kind": "cli",
                    "invoke_argv": invoke_argv,
                }
            },
            "edges": [{"from_node": node_id, "to_node": None}],
            "interface": INTERFACE,
        },
    )
    assert create.status_code == 200, create.text
    _ = await _seed_agent(
        flows_client_http,
        headers,
        flow_id=flow_id,
        node_id=node_id,
    )
    sdk = FlowUIClient(FLOWS_BASE_URL, flow_id=flow_id, headers=headers, timeout=120.0)
    _ = await sdk.open(context_id=f"ctx-ca-{unique_id}")
    prompt = f"hello-{unique_id}"
    turn = await sdk.send(prompt)
    assert turn.status == "completed"
    assert prompt in turn.response


@pytest.mark.asyncio
async def test_code_agent_composition_with_remote_flow_and_code(
    flows_client_http: AsyncClient,
    office_service,
    guest_runtime_service,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    _ = office_service, guest_runtime_service
    require_s3_configured()
    headers = code_agent_headers(auth_headers_system)
    echo_flow_id = f"ca_echo_{unique_id}"
    echo = await flows_client_http.post(
        "/flows/api/v1/flows/",
        headers=headers,
        json={
            "flow_id": echo_flow_id,
            "name": echo_flow_id,
            "entry": "main",
            "nodes": {"main": {"type": "code", "code": ECHO_CODE}},
            "edges": [{"from_node": "main", "to_node": None}],
        },
    )
    assert echo.status_code == 200, echo.text
    flow_id = f"ca_comp_{unique_id}"
    invoke_argv = ["python3", "main.py"]
    remote_url = f"http://127.0.0.1:9001/flows/api/v1/{echo_flow_id}"
    create = await flows_client_http.post(
        "/flows/api/v1/flows/",
        headers=headers,
        json={
            "flow_id": flow_id,
            "name": flow_id,
            "entry": "agent_a",
            "nodes": {
                "agent_a": {
                    "type": "code_agent",
                    "language": "python",
                    "invoke_kind": "cli",
                    "invoke_argv": invoke_argv,
                },
                "agent_b": {
                    "type": "code_agent",
                    "language": "python",
                    "invoke_kind": "cli",
                    "invoke_argv": invoke_argv,
                },
                "remote": {
                    "type": "remote_flow",
                    "url": remote_url,
                    "branch_id": "default",
                },
                "merge": {"type": "code", "code": MERGE_CODE},
            },
            "edges": [
                {"from_node": "agent_a", "to_node": "agent_b"},
                {"from_node": "agent_b", "to_node": "remote"},
                {"from_node": "remote", "to_node": "merge"},
                {"from_node": "merge", "to_node": None},
            ],
            "interface": INTERFACE,
        },
    )
    assert create.status_code == 200, create.text
    digest_a = await _seed_agent(flows_client_http, headers, flow_id=flow_id, node_id="agent_a")
    digest_b = await _seed_agent(flows_client_http, headers, flow_id=flow_id, node_id="agent_b")
    assert digest_a.startswith("inprocess:")
    assert digest_b.startswith("inprocess:")
    sdk = FlowUIClient(FLOWS_BASE_URL, flow_id=flow_id, headers=headers, timeout=120.0)
    _ = await sdk.open(context_id=f"ctx-comp-{unique_id}")
    prompt = f"comp-{unique_id}"
    turn = await sdk.send(prompt)
    assert turn.status == "completed"
    assert prompt in turn.response
    assert f"ECHO:{prompt}" in turn.response
    status_a = await flows_client_http.get(
        f"/flows/api/v1/flows/{flow_id}/nodes/agent_a/code-agent",
        headers=headers,
        params={"branch_id": "default"},
    )
    status_b = await flows_client_http.get(
        f"/flows/api/v1/flows/{flow_id}/nodes/agent_b/code-agent",
        headers=headers,
        params={"branch_id": "default"},
    )
    assert status_a.status_code == 200, status_a.text
    assert status_b.status_code == 200, status_b.text
    assert status_a.json()["catalog_id"] != status_b.json()["catalog_id"]


@pytest.mark.asyncio
async def test_code_agent_node_cli(
    flows_client_http: AsyncClient,
    office_service: object,
    guest_runtime_service: object,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    _ = office_service, guest_runtime_service
    require_s3_configured()
    _require_node_binary()
    headers = code_agent_headers(auth_headers_system)
    flow_id = f"ca_node_{unique_id}"
    node_id = "agent"
    create = await flows_client_http.post(
        "/flows/api/v1/flows/",
        headers=headers,
        json={
            "flow_id": flow_id,
            "name": flow_id,
            "entry": node_id,
            "nodes": {
                node_id: {
                    "type": "code_agent",
                    "language": "node",
                    "invoke_kind": "cli",
                    "invoke_argv": ["node", "main.js"],
                }
            },
            "edges": [{"from_node": node_id, "to_node": None}],
            "interface": INTERFACE,
        },
    )
    assert create.status_code == 200, create.text
    _ = await _seed_source(
        flows_client_http,
        headers,
        flow_id=flow_id,
        node_id=node_id,
        original_name="main.js",
        content=example_cli_node_bytes(),
        invoke_argv=["node", "main.js"],
        language="node",
    )
    sdk = FlowUIClient(FLOWS_BASE_URL, flow_id=flow_id, headers=headers, timeout=120.0)
    _ = await sdk.open(context_id=f"ctx-node-{unique_id}")
    prompt = f"hello-node-{unique_id}"
    turn = await sdk.send(prompt)
    assert turn.status == "completed"
    assert prompt in turn.response


@pytest.mark.asyncio
async def test_code_agent_python_a2a_and_direct_farm(
    flows_client_http: AsyncClient,
    office_service: object,
    guest_runtime_service: object,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    _ = office_service, guest_runtime_service
    require_s3_configured()
    headers = code_agent_headers(auth_headers_system)
    flow_id = f"ca_a2a_{unique_id}"
    node_id = "agent"
    listen_port = _unused_tcp_port()
    create = await flows_client_http.post(
        "/flows/api/v1/flows/",
        headers=headers,
        json={
            "flow_id": flow_id,
            "name": flow_id,
            "entry": node_id,
            "nodes": {
                node_id: {
                    "type": "code_agent",
                    "language": "python",
                    "invoke_kind": "a2a",
                    "invoke_listen_port": listen_port,
                    "invoke_argv": ["python3", "server.py"],
                }
            },
            "edges": [{"from_node": node_id, "to_node": None}],
            "interface": INTERFACE,
        },
    )
    assert create.status_code == 200, create.text
    _ = await _seed_source(
        flows_client_http,
        headers,
        flow_id=flow_id,
        node_id=node_id,
        original_name="server.py",
        content=example_a2a_python_bytes(),
        invoke_argv=["python3", "server.py"],
        invoke_kind="a2a",
        invoke_listen_port=listen_port,
    )
    sdk = FlowUIClient(FLOWS_BASE_URL, flow_id=flow_id, headers=headers, timeout=120.0)
    _ = await sdk.open(context_id=f"ctx-a2a-{unique_id}")
    prompt = f"hello-a2a-{unique_id}"
    turn = await sdk.send(prompt)
    assert turn.status == "completed"
    assert prompt in turn.response
    farm_url = f"http://127.0.0.1:9024/guest-runtime/api/v1/a2a/{flow_id}/{node_id}"
    a2a = A2AClient(timeout=60.0)
    direct_prompt = f"direct-{unique_id}"
    sent = await a2a.send_message(
        farm_url,
        parts=[{"text": direct_prompt}],
        context_id=f"ctx-direct-{unique_id}",
    )
    assert sent.status == "completed"
    status = sent.task.get("status")
    if not isinstance(status, dict):
        raise AssertionError(f"farm task status missing: {sent.task}")
    assert status.get("state") == "TASK_STATE_COMPLETED"
    assert direct_prompt in sent.response
    task_id = sent.task.get("id")
    if not isinstance(task_id, str) or task_id.strip() == "":
        raise AssertionError("farm task id required")
    fetched = await a2a.get_task(farm_url, task_id)
    fetched_status = fetched.task.get("status")
    if not isinstance(fetched_status, dict):
        raise AssertionError(f"GetTask status missing: {fetched.task}")
    assert fetched_status.get("state") == "TASK_STATE_COMPLETED"


@pytest.mark.asyncio
async def test_code_then_code_agent(
    flows_client_http: AsyncClient,
    office_service: object,
    guest_runtime_service: object,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    _ = office_service, guest_runtime_service
    require_s3_configured()
    headers = code_agent_headers(auth_headers_system)
    flow_id = f"ca_c2a_{unique_id}"
    invoke_argv = ["python3", "main.py"]
    create = await flows_client_http.post(
        "/flows/api/v1/flows/",
        headers=headers,
        json={
            "flow_id": flow_id,
            "name": flow_id,
            "entry": "echo",
            "nodes": {
                "echo": {"type": "code", "code": ECHO_CODE},
                "agent": {
                    "type": "code_agent",
                    "language": "python",
                    "invoke_kind": "cli",
                    "invoke_argv": invoke_argv,
                },
            },
            "edges": [
                {"from_node": "echo", "to_node": "agent"},
                {"from_node": "agent", "to_node": None},
            ],
            "interface": INTERFACE,
        },
    )
    assert create.status_code == 200, create.text
    _ = await _seed_agent(flows_client_http, headers, flow_id=flow_id, node_id="agent")
    sdk = FlowUIClient(FLOWS_BASE_URL, flow_id=flow_id, headers=headers, timeout=120.0)
    _ = await sdk.open(context_id=f"ctx-c2a-{unique_id}")
    prompt = f"c2a-{unique_id}"
    turn = await sdk.send(prompt)
    assert turn.status == "completed"
    assert prompt in turn.response


@pytest.mark.asyncio
async def test_code_agent_then_code(
    flows_client_http: AsyncClient,
    office_service: object,
    guest_runtime_service: object,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    _ = office_service, guest_runtime_service
    require_s3_configured()
    headers = code_agent_headers(auth_headers_system)
    flow_id = f"ca_a2c_{unique_id}"
    invoke_argv = ["python3", "main.py"]
    create = await flows_client_http.post(
        "/flows/api/v1/flows/",
        headers=headers,
        json={
            "flow_id": flow_id,
            "name": flow_id,
            "entry": "agent",
            "nodes": {
                "agent": {
                    "type": "code_agent",
                    "language": "python",
                    "invoke_kind": "cli",
                    "invoke_argv": invoke_argv,
                },
                "merge": {"type": "code", "code": MERGE_CODE},
            },
            "edges": [
                {"from_node": "agent", "to_node": "merge"},
                {"from_node": "merge", "to_node": None},
            ],
            "interface": INTERFACE,
        },
    )
    assert create.status_code == 200, create.text
    _ = await _seed_agent(flows_client_http, headers, flow_id=flow_id, node_id="agent")
    sdk = FlowUIClient(FLOWS_BASE_URL, flow_id=flow_id, headers=headers, timeout=120.0)
    _ = await sdk.open(context_id=f"ctx-a2c-{unique_id}")
    prompt = f"a2c-{unique_id}"
    turn = await sdk.send(prompt)
    assert turn.status == "completed"
    assert f"{prompt}|{prompt}" in turn.response


@pytest.mark.asyncio
async def test_code_agent_python_and_node_same_graph(
    flows_client_http: AsyncClient,
    office_service: object,
    guest_runtime_service: object,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    _ = office_service, guest_runtime_service
    require_s3_configured()
    _require_node_binary()
    headers = code_agent_headers(auth_headers_system)
    flow_id = f"ca_pn_{unique_id}"
    create = await flows_client_http.post(
        "/flows/api/v1/flows/",
        headers=headers,
        json={
            "flow_id": flow_id,
            "name": flow_id,
            "entry": "py",
            "nodes": {
                "py": {
                    "type": "code_agent",
                    "language": "python",
                    "invoke_kind": "cli",
                    "invoke_argv": ["python3", "main.py"],
                },
                "nd": {
                    "type": "code_agent",
                    "language": "node",
                    "invoke_kind": "cli",
                    "invoke_argv": ["node", "main.js"],
                },
            },
            "edges": [
                {"from_node": "py", "to_node": "nd"},
                {"from_node": "nd", "to_node": None},
            ],
            "interface": INTERFACE,
        },
    )
    assert create.status_code == 200, create.text
    _ = await _seed_source(
        flows_client_http,
        headers,
        flow_id=flow_id,
        node_id="py",
        original_name="main.py",
        content=example_main_py_bytes(),
        invoke_argv=["python3", "main.py"],
    )
    _ = await _seed_source(
        flows_client_http,
        headers,
        flow_id=flow_id,
        node_id="nd",
        original_name="main.js",
        content=example_cli_node_bytes(),
        invoke_argv=["node", "main.js"],
        language="node",
    )
    sdk = FlowUIClient(FLOWS_BASE_URL, flow_id=flow_id, headers=headers, timeout=120.0)
    _ = await sdk.open(context_id=f"ctx-pn-{unique_id}")
    prompt = f"py-node-{unique_id}"
    turn = await sdk.send(prompt)
    assert turn.status == "completed"
    assert prompt in turn.response


@pytest.mark.asyncio
async def test_code_agent_fail_cli_logs(
    flows_client_http: AsyncClient,
    office_service: object,
    guest_runtime_service: object,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    _ = office_service, guest_runtime_service
    require_s3_configured()
    headers = code_agent_headers(auth_headers_system)
    flow_id = f"ca_fail_{unique_id}"
    node_id = "agent"
    create = await flows_client_http.post(
        "/flows/api/v1/flows/",
        headers=headers,
        json={
            "flow_id": flow_id,
            "name": flow_id,
            "entry": node_id,
            "nodes": {
                node_id: {
                    "type": "code_agent",
                    "language": "python",
                    "invoke_kind": "cli",
                    "invoke_argv": ["python3", "main.py"],
                }
            },
            "edges": [{"from_node": node_id, "to_node": None}],
            "interface": INTERFACE,
        },
    )
    assert create.status_code == 200, create.text
    _ = await _seed_source(
        flows_client_http,
        headers,
        flow_id=flow_id,
        node_id=node_id,
        original_name="main.py",
        content=example_fail_cli_bytes(),
        invoke_argv=["python3", "main.py"],
    )
    sdk = FlowUIClient(FLOWS_BASE_URL, flow_id=flow_id, headers=headers, timeout=120.0)
    _ = await sdk.open(context_id=f"ctx-fail-{unique_id}")
    await _send_expect_invoke_failure(sdk, f"fail-{unique_id}")
    logs = await code_agent_logs(flows_client_http, headers, flow_id=flow_id, node_id=node_id)
    serialized = "\n".join(str(item) for item in logs)
    assert "guest.invoke.failed" in serialized
    assert "guest fail_cli" in serialized


@pytest.mark.asyncio
async def test_code_agent_ensure_lease_billing_blocked(
    flows_client_http: AsyncClient,
    office_service: object,
    guest_runtime_service: object,
    frontend_di,
    unique_id: str,
) -> None:
    _ = office_service, guest_runtime_service
    require_s3_configured()
    company_id = f"co_guest_zero_{unique_id}"
    user_id = f"u_guest_zero_{unique_id}"
    company = make_test_company(
        company_id=company_id,
        name="Zero guest",
        owner_user_id=user_id,
        members={user_id: ["owner", "admin"]},
        balance=0.0,
        subdomain=f"zg{unique_id[:12]}",
    )
    user = User(
        user_id=user_id,
        name="Zero Guest",
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
    flow_id = f"ca_bill_{unique_id}"
    node_id = "agent"
    invoke_argv = ["python3", "main.py"]
    create = await flows_client_http.post(
        "/flows/api/v1/flows/",
        headers=headers,
        json={
            "flow_id": flow_id,
            "name": flow_id,
            "entry": node_id,
            "nodes": {
                node_id: {
                    "type": "code_agent",
                    "language": "python",
                    "invoke_kind": "cli",
                    "invoke_argv": invoke_argv,
                }
            },
            "edges": [{"from_node": node_id, "to_node": None}],
            "interface": INTERFACE,
        },
    )
    assert create.status_code == 200, create.text
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
    assert digest.startswith("inprocess:")
    _catalog, files = await code_agent_status_files(
        flows_client_http, headers, flow_id=flow_id, node_id=node_id
    )
    _ = _catalog
    body = guest_ensure_lease_request(
        flow_id=flow_id,
        node_id=node_id,
        company_id=company_id,
        user_id=user_id,
        catalog_id=catalog_id,
        files=files,
        unique_id=unique_id,
        invoke_argv=invoke_argv,
        language=GuestLanguage.PYTHON,
        invoke_kind=GuestInvokeKind.CLI,
    )
    with pytest.raises(ServiceClientError) as blocked:
        await GuestRuntimeClient().ensure_lease(body)
    assert blocked.value.status_code == 403


@pytest.mark.asyncio
async def test_llm_node_then_code_agent(
    flows_client_http: AsyncClient,
    office_service: object,
    guest_runtime_service: object,
    auth_headers_system: dict[str, str],
    mock_llm_redis: MockLlmQueue,
    unique_id: str,
) -> None:
    _ = office_service, guest_runtime_service
    require_s3_configured()
    headers = code_agent_headers(auth_headers_system)
    flow_id = f"ca_llm_{unique_id}"
    llm_text = f"llm-out-{unique_id}"
    await mock_llm_redis(
        [
            {"type": "text", "content": llm_text},
            {"type": "text", "content": llm_text},
        ]
    )
    create = await flows_client_http.post(
        "/flows/api/v1/flows/",
        headers=headers,
        json={
            "flow_id": flow_id,
            "name": flow_id,
            "entry": "think",
            "nodes": {
                "think": {
                    "type": "llm_node",
                    "prompt": "Отвечай кратко.",
                    "tools": [],
                    "llm": {"provider": "mock", "model": "mock-gpt-4"},
                },
                "agent": {
                    "type": "code_agent",
                    "language": "python",
                    "invoke_kind": "cli",
                    "invoke_argv": ["python3", "main.py"],
                },
            },
            "edges": [
                {"from_node": "think", "to_node": "agent"},
                {"from_node": "agent", "to_node": None},
            ],
            "interface": INTERFACE,
        },
    )
    assert create.status_code == 200, create.text
    _ = await _seed_agent(flows_client_http, headers, flow_id=flow_id, node_id="agent")
    sdk = FlowUIClient(FLOWS_BASE_URL, flow_id=flow_id, headers=headers, timeout=120.0)
    _ = await sdk.open(context_id=f"ctx-llm-{unique_id}")
    prompt = f"llm-{unique_id}"
    turn = await sdk.send(prompt)
    assert turn.status == "completed"
    assert prompt in turn.response or llm_text in turn.response


@pytest.mark.asyncio
async def test_code_agent_guest_llm_proxy(
    flows_client_http: AsyncClient,
    office_service: object,
    guest_runtime_service: object,
    auth_headers_system: dict[str, str],
    mock_llm_redis: MockLlmQueue,
    unique_id: str,
) -> None:
    _ = office_service, guest_runtime_service
    require_s3_configured()
    headers = code_agent_headers(auth_headers_system)
    flow_id = f"ca_gllm_{unique_id}"
    node_id = "agent"
    llm_text = f"guest-llm-{unique_id}"
    await mock_llm_redis([{"type": "text", "content": llm_text}])
    create = await flows_client_http.post(
        "/flows/api/v1/flows/",
        headers=headers,
        json={
            "flow_id": flow_id,
            "name": flow_id,
            "entry": node_id,
            "nodes": {
                node_id: {
                    "type": "code_agent",
                    "language": "python",
                    "invoke_kind": "cli",
                    "invoke_argv": ["python3", "main.py"],
                }
            },
            "edges": [{"from_node": node_id, "to_node": None}],
            "interface": INTERFACE,
        },
    )
    assert create.status_code == 200, create.text
    _ = await _seed_source(
        flows_client_http,
        headers,
        flow_id=flow_id,
        node_id=node_id,
        original_name="main.py",
        content=example_llm_cli_bytes(),
        invoke_argv=["python3", "main.py"],
    )
    sdk = FlowUIClient(FLOWS_BASE_URL, flow_id=flow_id, headers=headers, timeout=120.0)
    _ = await sdk.open(context_id=f"ctx-gllm-{unique_id}")
    turn = await sdk.send(f"ask-{unique_id}")
    assert turn.status == "completed"
    assert llm_text in turn.response


@pytest.mark.asyncio
async def test_code_agent_interrupt(
    flows_client_http: AsyncClient,
    office_service: object,
    guest_runtime_service: object,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    _ = office_service, guest_runtime_service
    require_s3_configured()
    headers = code_agent_headers(auth_headers_system)
    flow_id = f"ca_int_{unique_id}"
    node_id = "agent"
    create = await flows_client_http.post(
        "/flows/api/v1/flows/",
        headers=headers,
        json={
            "flow_id": flow_id,
            "name": flow_id,
            "entry": node_id,
            "nodes": {
                node_id: {
                    "type": "code_agent",
                    "language": "python",
                    "invoke_kind": "cli",
                    "invoke_argv": ["python3", "main.py"],
                }
            },
            "edges": [{"from_node": node_id, "to_node": None}],
            "interface": INTERFACE,
        },
    )
    assert create.status_code == 200, create.text
    _ = await _seed_source(
        flows_client_http,
        headers,
        flow_id=flow_id,
        node_id=node_id,
        original_name="main.py",
        content=example_interrupt_cli_bytes(),
        invoke_argv=["python3", "main.py"],
    )
    sdk = FlowUIClient(FLOWS_BASE_URL, flow_id=flow_id, headers=headers, timeout=120.0)
    _ = await sdk.open(context_id=f"ctx-int-{unique_id}")
    prompt = f"need-help-{unique_id}"
    turn = await sdk.send(prompt)
    assert turn.status == "input-required"
    artifact_ids = [item.get("artifactId") for item in turn.artifacts if isinstance(item, dict)]
    assert any(isinstance(item, str) and "interrupt" in item for item in artifact_ids)


@pytest.mark.asyncio
async def test_code_agent_platform_effects(
    flows_client_http: AsyncClient,
    office_service: object,
    guest_runtime_service: object,
    capability_gateway_service: object,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    _ = office_service, guest_runtime_service, capability_gateway_service
    require_s3_configured()
    headers = code_agent_headers(auth_headers_system)
    flow_id = f"ca_fx_{unique_id}"
    node_id = "agent"
    create = await flows_client_http.post(
        "/flows/api/v1/flows/",
        headers=headers,
        json={
            "flow_id": flow_id,
            "name": flow_id,
            "entry": node_id,
            "nodes": {
                node_id: {
                    "type": "code_agent",
                    "language": "python",
                    "invoke_kind": "cli",
                    "invoke_argv": ["python3", "main.py"],
                }
            },
            "edges": [{"from_node": node_id, "to_node": None}],
            "interface": INTERFACE,
        },
    )
    assert create.status_code == 200, create.text
    _ = await _seed_source(
        flows_client_http,
        headers,
        flow_id=flow_id,
        node_id=node_id,
        original_name="main.py",
        content=example_effects_cli_bytes(),
        invoke_argv=["python3", "main.py"],
    )
    sdk = FlowUIClient(FLOWS_BASE_URL, flow_id=flow_id, headers=headers, timeout=120.0)
    _ = await sdk.open(context_id=f"ctx-fx-{unique_id}")
    prompt = f"fx-{unique_id}"
    turn = await sdk.send(prompt)
    assert turn.status == "completed"
    assert prompt in turn.response


async def _skip_unless_docker_farm() -> None:
    if get_settings().guest_runtime.executor != "docker":
        pytest.skip("guest_runtime executor is not docker")
    try:
        await require_docker()
    except RuntimeError as exc:
        pytest.skip(str(exc))


@pytest.mark.asyncio
@pytest.mark.timeout(600, func_only=True)
async def test_code_agent_docker_python3_cli(
    flows_client_http: AsyncClient,
    office_service: object,
    guest_runtime_service: object,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    _ = office_service, guest_runtime_service
    require_s3_configured()
    await _skip_unless_docker_farm()
    headers = code_agent_headers(auth_headers_system)
    flow_id = f"ca_dpy_{unique_id}"
    node_id = "agent"
    create = await flows_client_http.post(
        "/flows/api/v1/flows/",
        headers=headers,
        json={
            "flow_id": flow_id,
            "name": flow_id,
            "entry": node_id,
            "nodes": {
                node_id: {
                    "type": "code_agent",
                    "language": "python",
                    "invoke_kind": "cli",
                    "invoke_argv": ["python3", "main.py"],
                }
            },
            "edges": [{"from_node": node_id, "to_node": None}],
            "interface": INTERFACE,
        },
    )
    assert create.status_code == 200, create.text
    _ = await ensure_code_agent_catalog(
        flows_client_http, headers, flow_id=flow_id, node_id=node_id
    )
    await upload_code_agent_file(
        flows_client_http,
        headers,
        flow_id=flow_id,
        node_id=node_id,
        original_name="main.py",
        content=example_echo_cli_bytes(),
    )
    digest = await rebuild_code_agent(
        flows_client_http,
        headers,
        flow_id=flow_id,
        node_id=node_id,
        invoke_argv=["python3", "main.py"],
    )
    if digest.startswith("inprocess:"):
        raise AssertionError(f"docker executor returned inprocess digest: {digest}")
    sdk = FlowUIClient(FLOWS_BASE_URL, flow_id=flow_id, headers=headers, timeout=600.0)
    _ = await sdk.open(context_id=f"ctx-dpy-{unique_id}")
    prompt = f"hello-docker-{unique_id}"
    turn = await sdk.send(prompt)
    assert turn.status == "completed"
    assert prompt in turn.response


SET_TICKET_CODE = (
    "async def run(args, state):\n"
    "    content = state.get('content')\n"
    "    if not isinstance(content, str):\n"
    "        raise ValueError('content required')\n"
    "    state['ticket'] = content\n"
    "    return state\n"
)

MAPPING_CLI = b"""import json
import os
import sys
from core.models.identity_models import Company

ticket = os.environ.get("TICKET")
if ticket is None or ticket.strip() == "":
    raise RuntimeError("TICKET is required")
raw = os.environ.get("PLATFORM_A2A_METADATA")
if raw is None or raw.strip() == "":
    raise RuntimeError("PLATFORM_A2A_METADATA is required")
metadata = json.loads(raw)
if not isinstance(metadata, dict):
    raise RuntimeError("PLATFORM_A2A_METADATA must be an object")
guest_state = metadata.get("state")
if not isinstance(guest_state, dict):
    raise RuntimeError("metadata.state must be an object")
if guest_state.get("ticket") != ticket:
    raise RuntimeError("metadata.state.ticket mismatch")
extra = " ".join(sys.argv[1:])
sys.stdout.write(json.dumps({"text": extra, "echo_ticket": ticket}, ensure_ascii=False))
sys.stdout.write("\\n")
"""

MAPPING_INTERFACE = {
    "start_page_id": "main",
    "pages": [
        {
            "page_id": "main",
            "title": "Code agent",
            "blocks": [
                {"type": "conversation", "block_id": "conversation"},
                {"type": "text", "block_id": "ticket-view", "markdown": "{ticket}"},
                {"type": "text", "block_id": "echo-view", "markdown": "{echo_ticket}"},
            ],
        }
    ],
}


@pytest.mark.asyncio
async def test_code_agent_guest_env_and_metadata_to_output_mapping(
    flows_client_http: AsyncClient,
    office_service,
    guest_runtime_service,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    _ = office_service, guest_runtime_service
    require_s3_configured()
    headers = code_agent_headers(auth_headers_system)
    flow_id = f"ca_map_{unique_id}"
    node_id = "agent"
    create = await flows_client_http.post(
        "/flows/api/v1/flows/",
        headers=headers,
        json={
            "flow_id": flow_id,
            "name": flow_id,
            "entry": "seed",
            "nodes": {
                "seed": {"type": "code", "code": SET_TICKET_CODE},
                node_id: {
                    "type": "code_agent",
                    "language": "python",
                    "invoke_kind": "cli",
                    "invoke_argv": ["python3", "main.py"],
                    "guest_env": {"TICKET": "@state:ticket"},
                    "metadata_template": '{"state": "@state"}',
                    "output_mapping": {"echo_ticket": "echo_ticket"},
                },
            },
            "edges": [
                {"from_node": "seed", "to_node": node_id},
                {"from_node": node_id, "to_node": None},
            ],
            "interface": MAPPING_INTERFACE,
        },
    )
    assert create.status_code == 200, create.text
    _ = await _seed_source(
        flows_client_http,
        headers,
        flow_id=flow_id,
        node_id=node_id,
        original_name="main.py",
        content=MAPPING_CLI,
        invoke_argv=["python3", "main.py"],
    )
    sdk = FlowUIClient(FLOWS_BASE_URL, flow_id=flow_id, headers=headers, timeout=120.0)
    _ = await sdk.open(context_id=f"ctx-map-{unique_id}")
    prompt = f"ticket-{unique_id}"
    turn = await sdk.send(prompt)
    assert turn.status == "completed"
    assert prompt in turn.response
    guest_state_ids = [
        artifact.get("artifactId") for artifact in turn.artifacts if isinstance(artifact, dict)
    ]
    assert f"code_agent:{node_id}:state" in guest_state_ids, guest_state_ids
    assert sdk.state.get("ticket") == prompt, sdk.state
    assert sdk.state.get("echo_ticket") == prompt, sdk.state
