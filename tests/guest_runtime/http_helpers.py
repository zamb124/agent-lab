from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from httpx2 import AsyncClient

from core.config import get_settings
from core.files.types import ext_to_mime
from core.guest_runtime.models import (
    CodeAgentNodeStatusResponse,
    CodeAgentSourceFile,
    GuestEnsureLeaseRequest,
    GuestInvokeKind,
    GuestLanguage,
)
from core.types import require_json_object
from tests.files.chunked_upload_helpers import (
    chunked_upload_file,
    code_agent_source_upload_spec_json,
)

EXAMPLES_ROOT = Path(__file__).resolve().parents[2] / "apps" / "guest_runtime" / "examples"

FLOWS_FILES_PREFIX = "/flows/api/v1/files"
NAMESPACE_HEADER = {"X-Platform-Namespace": "default"}


def code_agent_headers(auth_headers: Mapping[str, str]) -> dict[str, str]:
    return {**auth_headers, **NAMESPACE_HEADER}


def example_bytes(*relative: str) -> bytes:
    path = EXAMPLES_ROOT.joinpath(*relative)
    payload = path.read_bytes()
    if len(payload) == 0:
        raise ValueError(f"{path} is empty")
    return payload


def example_main_py_bytes() -> bytes:
    return example_bytes("cli_python", "main.py")


def example_cli_node_bytes() -> bytes:
    return example_bytes("cli_node", "main.js")


def example_a2a_python_bytes() -> bytes:
    return example_bytes("a2a_python", "server.py")


def example_fail_cli_bytes() -> bytes:
    return example_bytes("fail_cli", "main.py")


def example_interrupt_cli_bytes() -> bytes:
    return example_bytes("interrupt_cli", "main.py")


def example_effects_cli_bytes() -> bytes:
    return example_bytes("effects_cli", "main.py")


def example_llm_cli_bytes() -> bytes:
    return example_bytes("cli_llm", "main.py")


def example_echo_cli_bytes() -> bytes:
    return (
        b"import json\n"
        b"import sys\n"
        b"\n"
        b'extra = " ".join(sys.argv[1:])\n'
        b'sys.stdout.write(json.dumps({"text": extra}, ensure_ascii=False))\n'
        b'sys.stdout.write("\\n")\n'
    )


async def create_code_agent_flow(
    flows_client: AsyncClient,
    headers: Mapping[str, str],
    *,
    flow_id: str,
    node_id: str,
    invoke_argv: list[str],
    language: str = "python",
    invoke_kind: str = "cli",
    invoke_listen_port: int | None = None,
    extra_nodes: dict[str, object] | None = None,
    extra_edges: list[dict[str, object]] | None = None,
    entry: str | None = None,
    interface: dict[str, object] | None = None,
) -> None:
    node: dict[str, object] = {
        "type": "code_agent",
        "language": language,
        "invoke_kind": invoke_kind,
        "invoke_argv": invoke_argv,
    }
    if invoke_listen_port is not None:
        node["invoke_listen_port"] = invoke_listen_port
    nodes: dict[str, object] = {node_id: node}
    if extra_nodes is not None:
        nodes.update(extra_nodes)
    edges: list[dict[str, object]] = (
        extra_edges if extra_edges is not None else [{"from_node": node_id, "to_node": None}]
    )
    body: dict[str, object] = {
        "flow_id": flow_id,
        "name": flow_id,
        "entry": entry if entry is not None else node_id,
        "nodes": nodes,
        "edges": edges,
    }
    if interface is not None:
        body["interface"] = interface
    response = await flows_client.post(
        "/flows/api/v1/flows/",
        headers=headers,
        json=body,
    )
    assert response.status_code == 200, response.text


async def ensure_code_agent_catalog(
    flows_client: AsyncClient,
    headers: Mapping[str, str],
    *,
    flow_id: str,
    node_id: str,
) -> str:
    response = await flows_client.post(
        f"/flows/api/v1/flows/{flow_id}/nodes/{node_id}/code-agent/ensure-source",
        headers=headers,
        params={"branch_id": "default"},
    )
    assert response.status_code == 200, response.text
    payload = require_json_object(response.json(), "code_agent.ensure_source")
    catalog_id = payload.get("catalog_id")
    if not isinstance(catalog_id, str) or catalog_id.strip() == "":
        raise AssertionError(f"catalog_id missing: {payload}")
    return catalog_id


async def upload_code_agent_file(
    flows_client: AsyncClient,
    headers: Mapping[str, str],
    *,
    flow_id: str,
    node_id: str,
    original_name: str,
    content: bytes,
    relative_dir: str | None = None,
) -> str:
    suffix = Path(original_name).suffix.lower()
    complete = await chunked_upload_file(
        flows_client,
        headers,
        content=content,
        original_name=original_name,
        content_type=ext_to_mime(suffix),
        spec_json=code_agent_source_upload_spec_json(
            flow_id=flow_id,
            node_id=node_id,
            relative_dir=relative_dir,
        ),
        files_api_prefix=FLOWS_FILES_PREFIX,
    )
    assert complete.status_code == 200, complete.text
    payload = require_json_object(complete.json(), "code_agent.upload")
    file_id = payload.get("file_id")
    if not isinstance(file_id, str) or file_id.strip() == "":
        raise AssertionError(f"file_id missing: {payload}")
    return file_id


async def rebuild_code_agent(
    flows_client: AsyncClient,
    headers: Mapping[str, str],
    *,
    flow_id: str,
    node_id: str,
    invoke_argv: list[str],
    language: str = "python",
    invoke_kind: str = "cli",
    invoke_listen_port: int | None = None,
    egress_hosts: list[str] | None = None,
    git_url: str | None = None,
    source_sha: str | None = None,
    timeout: float = 600.0,
) -> str:
    body: dict[str, object] = {
        "language": language,
        "invoke_kind": invoke_kind,
        "invoke_argv": invoke_argv,
        "invoke_listen_port": invoke_listen_port,
        "egress_hosts": [] if egress_hosts is None else egress_hosts,
        "git_url": git_url,
        "source_sha": source_sha,
    }
    response = await flows_client.post(
        f"/flows/api/v1/flows/{flow_id}/nodes/{node_id}/code-agent/rebuild",
        headers=headers,
        params={"branch_id": "default"},
        json=body,
        timeout=timeout,
    )
    assert response.status_code == 200, response.text
    payload = require_json_object(response.json(), "code_agent.rebuild")
    digest = payload.get("image_digest")
    if not isinstance(digest, str) or digest.strip() == "":
        raise AssertionError(f"image_digest missing: {payload}")
    return digest


async def code_agent_logs(
    flows_client: AsyncClient,
    headers: Mapping[str, str],
    *,
    flow_id: str,
    node_id: str,
) -> list[object]:
    response = await flows_client.get(
        f"/flows/api/v1/flows/{flow_id}/nodes/{node_id}/code-agent/logs",
        headers=headers,
        params={"branch_id": "default"},
    )
    assert response.status_code == 200, response.text
    payload = require_json_object(response.json(), "code_agent.logs")
    items = payload.get("items")
    if not isinstance(items, list):
        raise AssertionError(f"logs items missing: {payload}")
    return items


def guest_proxy_urls() -> tuple[str, str]:
    settings = get_settings()
    flows_base = settings.server.get_service_url("flows").rstrip("/")
    gateway = settings.server.get_service_url("capability_gateway").rstrip("/")
    if flows_base.strip() == "":
        raise RuntimeError("flows service url is required")
    if gateway.strip() == "":
        raise RuntimeError("capability_gateway service url is required")
    return f"{flows_base}/flows/api/v1/llm/v1", gateway


async def code_agent_status_files(
    flows_client: AsyncClient,
    headers: Mapping[str, str],
    *,
    flow_id: str,
    node_id: str,
) -> tuple[str, list[CodeAgentSourceFile]]:
    response = await flows_client.get(
        f"/flows/api/v1/flows/{flow_id}/nodes/{node_id}/code-agent",
        headers=headers,
        params={"branch_id": "default"},
    )
    assert response.status_code == 200, response.text
    payload = require_json_object(response.json(), "code_agent.status")
    catalog_id = payload.get("catalog_id")
    if not isinstance(catalog_id, str) or catalog_id.strip() == "":
        raise AssertionError(f"catalog_id missing: {payload}")
    raw_files = payload.get("files")
    if not isinstance(raw_files, list):
        raise AssertionError(f"files missing: {payload}")
    files = [CodeAgentSourceFile.model_validate(item) for item in raw_files]
    return catalog_id, files


def guest_ensure_lease_request(
    *,
    flow_id: str,
    node_id: str,
    company_id: str,
    user_id: str,
    catalog_id: str,
    files: list[CodeAgentSourceFile],
    unique_id: str,
    invoke_argv: list[str],
    language: GuestLanguage = GuestLanguage.PYTHON,
    invoke_kind: GuestInvokeKind = GuestInvokeKind.CLI,
    invoke_listen_port: int | None = None,
    idle_ttl_seconds: int | None = None,
    execution_token: str = "guest-test-token",
) -> GuestEnsureLeaseRequest:
    llm_url, gateway_url = guest_proxy_urls()
    return GuestEnsureLeaseRequest(
        flow_id=flow_id,
        node_id=node_id,
        company_id=company_id,
        user_id=user_id,
        catalog_id=catalog_id,
        language=language,
        invoke_kind=invoke_kind,
        invoke_argv=invoke_argv,
        invoke_listen_port=invoke_listen_port,
        files=files,
        execution_token=execution_token,
        llm_proxy_base_url=llm_url,
        capability_gateway_base_url=gateway_url,
        session_id=f"sess-{unique_id}",
        task_id=f"task-{unique_id}",
        context_id=f"ctx-{unique_id}",
        branch_id="default",
        channel="web",
        source_node_id=node_id,
        request_id=f"req-{unique_id}",
        trace_id=f"tr-{unique_id}",
        idle_ttl_seconds=idle_ttl_seconds,
    )


async def import_code_agent_git(
    flows_client: AsyncClient,
    headers: Mapping[str, str],
    *,
    flow_id: str,
    node_id: str,
    git_url: str,
    source_sha: str,
) -> CodeAgentNodeStatusResponse:
    response = await flows_client.post(
        f"/flows/api/v1/flows/{flow_id}/nodes/{node_id}/code-agent/import-git",
        headers=headers,
        params={"branch_id": "default"},
        json={"git_url": git_url, "source_sha": source_sha},
        timeout=180.0,
    )
    assert response.status_code == 200, response.text
    return CodeAgentNodeStatusResponse.model_validate(
        require_json_object(response.json(), "code_agent.import_git")
    )
