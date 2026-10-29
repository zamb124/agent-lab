from __future__ import annotations

import asyncio
import io
import os
import shutil
import zipfile
from pathlib import Path

import pytest
from httpx2 import AsyncClient

from tests.fixtures.s3 import require_s3_configured
from tests.guest_runtime.http_helpers import (
    code_agent_headers,
    create_code_agent_flow,
    ensure_code_agent_catalog,
    example_main_py_bytes,
    rebuild_code_agent,
    upload_code_agent_file,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(90, func_only=True)]


async def _create_python_cli(
    flows_client_http: AsyncClient,
    headers: dict[str, str],
    *,
    flow_id: str,
    node_id: str = "agent",
    invoke_argv: list[str] | None = None,
) -> None:
    await create_code_agent_flow(
        flows_client_http,
        headers,
        flow_id=flow_id,
        node_id=node_id,
        invoke_argv=["python", "main.py"] if invoke_argv is None else invoke_argv,
    )


async def test_code_agent_ensure_source_binds_documents_tree(
    flows_client_http: AsyncClient,
    office_client_http: AsyncClient,
    office_service,
    guest_runtime_service,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    _ = office_service, guest_runtime_service
    require_s3_configured()
    headers = code_agent_headers(auth_headers_system)
    flow_id = f"ca_src_{unique_id}"
    node_id = "agent"
    await _create_python_cli(flows_client_http, headers, flow_id=flow_id, node_id=node_id)
    catalog_id = await ensure_code_agent_catalog(
        flows_client_http, headers, flow_id=flow_id, node_id=node_id
    )
    file_id = await upload_code_agent_file(
        flows_client_http,
        headers,
        flow_id=flow_id,
        node_id=node_id,
        original_name="main.py",
        content=example_main_py_bytes(),
    )
    items = await office_client_http.get(
        f"/documents/api/v1/catalogs/{catalog_id}/items",
        headers=headers,
    )
    assert items.status_code == 200, items.text
    body = items.json()
    documents = body["documents"]
    titles = {item["title"] for item in documents}
    file_ids = {item["file_id"] for item in documents}
    assert "main.py" in titles
    assert file_id in file_ids
    status = await flows_client_http.get(
        f"/flows/api/v1/flows/{flow_id}/nodes/{node_id}/code-agent",
        headers=headers,
        params={"branch_id": "default"},
    )
    assert status.status_code == 200, status.text
    files = status.json()["files"]
    paths = {item["relative_path"] for item in files}
    assert "main.py" in paths


async def test_code_agent_nested_upload(
    flows_client_http: AsyncClient,
    office_service,
    guest_runtime_service,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    _ = office_service, guest_runtime_service
    require_s3_configured()
    headers = code_agent_headers(auth_headers_system)
    flow_id = f"ca_nested_{unique_id}"
    await _create_python_cli(flows_client_http, headers, flow_id=flow_id)
    await ensure_code_agent_catalog(
        flows_client_http, headers, flow_id=flow_id, node_id="agent"
    )
    await upload_code_agent_file(
        flows_client_http,
        headers,
        flow_id=flow_id,
        node_id="agent",
        original_name="util.py",
        content=b"VALUE = 1\n",
        relative_dir="src/lib",
    )
    status = await flows_client_http.get(
        f"/flows/api/v1/flows/{flow_id}/nodes/agent/code-agent",
        headers=headers,
        params={"branch_id": "default"},
    )
    assert status.status_code == 200, status.text
    paths = {item["relative_path"] for item in status.json()["files"]}
    assert "src/lib/util.py" in paths


async def test_code_agent_import_zip(
    flows_client_http: AsyncClient,
    office_service,
    guest_runtime_service,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    _ = office_service, guest_runtime_service
    require_s3_configured()
    headers = code_agent_headers(auth_headers_system)
    flow_id = f"ca_zip_{unique_id}"
    await _create_python_cli(flows_client_http, headers, flow_id=flow_id)
    await ensure_code_agent_catalog(
        flows_client_http, headers, flow_id=flow_id, node_id="agent"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("main.py", example_main_py_bytes())
        archive.writestr("pkg/helper.py", b"X = 1\n")
    zip_id = await upload_code_agent_file(
        flows_client_http,
        headers,
        flow_id=flow_id,
        node_id="agent",
        original_name="source.zip",
        content=buffer.getvalue(),
    )
    imported = await flows_client_http.post(
        f"/flows/api/v1/flows/{flow_id}/nodes/agent/code-agent/import-archive",
        headers=headers,
        params={"branch_id": "default"},
        json={"file_id": zip_id},
    )
    assert imported.status_code == 200, imported.text
    paths = {item["relative_path"] for item in imported.json()["files"]}
    assert "main.py" in paths
    assert "pkg/helper.py" in paths


async def test_code_agent_import_git_file_url(
    flows_client_http: AsyncClient,
    office_service,
    guest_runtime_service,
    auth_headers_system: dict[str, str],
    unique_id: str,
    tmp_path: Path,
) -> None:
    _ = office_service, guest_runtime_service
    require_s3_configured()
    headers = code_agent_headers(auth_headers_system)
    flow_id = f"ca_git_{unique_id}"
    await _create_python_cli(flows_client_http, headers, flow_id=flow_id)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_bytes(example_main_py_bytes())
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git is required for code_agent import-git test")
    env = dict(os.environ)
    env["GIT_AUTHOR_NAME"] = "code-agent-test"
    env["GIT_AUTHOR_EMAIL"] = "code-agent@example.test"
    env["GIT_COMMITTER_NAME"] = "code-agent-test"
    env["GIT_COMMITTER_EMAIL"] = "code-agent@example.test"
    env["GIT_TERMINAL_PROMPT"] = "0"

    async def _git(*args: str) -> str:
        process = await asyncio.create_subprocess_exec(
            git,
            *args,
            cwd=str(repo),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(out.decode("utf-8", errors="replace"))
        return out.decode("utf-8").strip()

    await _git("init")
    await _git("add", "main.py")
    await _git("commit", "-m", "seed")
    sha = await _git("rev-parse", "HEAD")
    imported = await flows_client_http.post(
        f"/flows/api/v1/flows/{flow_id}/nodes/agent/code-agent/import-git",
        headers=headers,
        params={"branch_id": "default"},
        json={"git_url": str(repo), "source_sha": sha},
    )
    assert imported.status_code == 200, imported.text
    paths = {item["relative_path"] for item in imported.json()["files"]}
    assert "main.py" in paths


async def test_code_agent_status_without_node_in_graph(
    flows_client_http: AsyncClient,
    office_service,
    guest_runtime_service,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    _ = office_service, guest_runtime_service
    require_s3_configured()
    headers = code_agent_headers(auth_headers_system)
    flow_id = f"ca_unsaved_{unique_id}"
    await _create_python_cli(flows_client_http, headers, flow_id=flow_id, node_id="saved")
    catalog_id = await ensure_code_agent_catalog(
        flows_client_http, headers, flow_id=flow_id, node_id="unsaved"
    )
    status = await flows_client_http.get(
        f"/flows/api/v1/flows/{flow_id}/nodes/unsaved/code-agent",
        headers=headers,
        params={"branch_id": "base"},
    )
    assert status.status_code == 200, status.text
    body = status.json()
    assert body["catalog_id"] == catalog_id
    assert body["files"] == []
    assert body["build_status"] == "none"


async def test_code_agent_import_git_without_node_in_graph(
    flows_client_http: AsyncClient,
    office_service,
    guest_runtime_service,
    auth_headers_system: dict[str, str],
    unique_id: str,
    tmp_path: Path,
) -> None:
    _ = office_service, guest_runtime_service
    require_s3_configured()
    headers = code_agent_headers(auth_headers_system)
    flow_id = f"ca_unsaved_git_{unique_id}"
    await _create_python_cli(flows_client_http, headers, flow_id=flow_id, node_id="saved")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_bytes(example_main_py_bytes())
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git is required for code_agent import-git test")
    env = dict(os.environ)
    env["GIT_AUTHOR_NAME"] = "code-agent-test"
    env["GIT_AUTHOR_EMAIL"] = "code-agent@example.test"
    env["GIT_COMMITTER_NAME"] = "code-agent-test"
    env["GIT_COMMITTER_EMAIL"] = "code-agent@example.test"
    env["GIT_TERMINAL_PROMPT"] = "0"

    async def _git(*args: str) -> str:
        process = await asyncio.create_subprocess_exec(
            git,
            *args,
            cwd=str(repo),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(out.decode("utf-8", errors="replace"))
        return out.decode("utf-8").strip()

    await _git("init")
    await _git("add", "main.py")
    await _git("commit", "-m", "seed")
    sha = await _git("rev-parse", "HEAD")
    imported = await flows_client_http.post(
        f"/flows/api/v1/flows/{flow_id}/nodes/unsaved/code-agent/import-git",
        headers=headers,
        params={"branch_id": "base"},
        json={"git_url": str(repo), "source_sha": sha},
    )
    assert imported.status_code == 200, imported.text
    body = imported.json()
    paths = {item["relative_path"] for item in body["files"]}
    assert "main.py" in paths
    flow = await flows_client_http.get(f"/flows/api/v1/flows/{flow_id}", headers=headers)
    assert flow.status_code == 200, flow.text
    nodes = flow.json()["nodes"]
    assert "unsaved" not in nodes


async def test_code_agent_rebuild_without_node_in_graph(
    flows_client_http: AsyncClient,
    office_service,
    guest_runtime_service,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    _ = office_service, guest_runtime_service
    require_s3_configured()
    headers = code_agent_headers(auth_headers_system)
    flow_id = f"ca_unsaved_rebuild_{unique_id}"
    await _create_python_cli(flows_client_http, headers, flow_id=flow_id, node_id="saved")
    await ensure_code_agent_catalog(
        flows_client_http, headers, flow_id=flow_id, node_id="unsaved"
    )
    await upload_code_agent_file(
        flows_client_http,
        headers,
        flow_id=flow_id,
        node_id="unsaved",
        original_name="main.py",
        content=example_main_py_bytes(),
    )
    digest = await rebuild_code_agent(
        flows_client_http,
        headers,
        flow_id=flow_id,
        node_id="unsaved",
        invoke_argv=["python3", "main.py"],
    )
    assert digest.startswith("inprocess:")
    flow = await flows_client_http.get(f"/flows/api/v1/flows/{flow_id}", headers=headers)
    assert flow.status_code == 200, flow.text
    assert "unsaved" not in flow.json()["nodes"]


async def test_code_agent_import_git_empty_sha_pins_head(
    flows_client_http: AsyncClient,
    office_service,
    guest_runtime_service,
    auth_headers_system: dict[str, str],
    unique_id: str,
    tmp_path: Path,
) -> None:
    _ = office_service, guest_runtime_service
    require_s3_configured()
    headers = code_agent_headers(auth_headers_system)
    flow_id = f"ca_git_head_{unique_id}"
    await _create_python_cli(flows_client_http, headers, flow_id=flow_id)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_bytes(example_main_py_bytes())
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git is required for code_agent import-git test")
    env = dict(os.environ)
    env["GIT_AUTHOR_NAME"] = "code-agent-test"
    env["GIT_AUTHOR_EMAIL"] = "code-agent@example.test"
    env["GIT_COMMITTER_NAME"] = "code-agent-test"
    env["GIT_COMMITTER_EMAIL"] = "code-agent@example.test"
    env["GIT_TERMINAL_PROMPT"] = "0"

    async def _git(*args: str) -> str:
        process = await asyncio.create_subprocess_exec(
            git,
            *args,
            cwd=str(repo),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(out.decode("utf-8", errors="replace"))
        return out.decode("utf-8").strip()

    await _git("init")
    await _git("add", "main.py")
    await _git("commit", "-m", "seed")
    sha = await _git("rev-parse", "HEAD")
    imported = await flows_client_http.post(
        f"/flows/api/v1/flows/{flow_id}/nodes/agent/code-agent/import-git",
        headers=headers,
        params={"branch_id": "default"},
        json={"git_url": str(repo), "source_sha": ""},
    )
    assert imported.status_code == 200, imported.text
    body = imported.json()
    assert body["source_sha"] == sha
    paths = {item["relative_path"] for item in body["files"]}
    assert "main.py" in paths


async def test_code_agent_import_git_short_commit_url_400(
    flows_client_http: AsyncClient,
    office_service,
    guest_runtime_service,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    _ = office_service, guest_runtime_service
    headers = code_agent_headers(auth_headers_system)
    flow_id = f"ca_git_nosh_{unique_id}"
    await _create_python_cli(flows_client_http, headers, flow_id=flow_id)
    response = await flows_client_http.post(
        f"/flows/api/v1/flows/{flow_id}/nodes/agent/code-agent/import-git",
        headers=headers,
        params={"branch_id": "default"},
        json={
            "git_url": "https://github.com/zub123123123/cheetah-agent/commit/abc123",
            "source_sha": "",
        },
    )
    assert response.status_code == 400, response.text


async def test_code_agent_copy_tree_and_delete(
    flows_client_http: AsyncClient,
    office_service,
    guest_runtime_service,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    _ = office_service, guest_runtime_service
    require_s3_configured()
    headers = code_agent_headers(auth_headers_system)
    flow_id = f"ca_copy_{unique_id}"
    create = await flows_client_http.post(
        "/flows/api/v1/flows/",
        headers=headers,
        json={
            "flow_id": flow_id,
            "name": flow_id,
            "entry": "src",
            "nodes": {
                "src": {
                    "type": "code_agent",
                    "language": "python",
                    "invoke_kind": "cli",
                    "invoke_argv": ["python", "main.py"],
                },
                "dst": {
                    "type": "code_agent",
                    "language": "python",
                    "invoke_kind": "cli",
                    "invoke_argv": ["python", "main.py"],
                },
            },
            "edges": [
                {"from_node": "src", "to_node": "dst"},
                {"from_node": "dst", "to_node": None},
            ],
        },
    )
    assert create.status_code == 200, create.text
    src_catalog = await ensure_code_agent_catalog(
        flows_client_http, headers, flow_id=flow_id, node_id="src"
    )
    await upload_code_agent_file(
        flows_client_http,
        headers,
        flow_id=flow_id,
        node_id="src",
        original_name="main.py",
        content=example_main_py_bytes(),
    )
    copied = await flows_client_http.post(
        f"/flows/api/v1/flows/{flow_id}/nodes/dst/code-agent/copy-tree",
        headers=headers,
        params={"branch_id": "default"},
        json={"from_catalog_id": src_catalog},
    )
    assert copied.status_code == 200, copied.text
    dst_status = await flows_client_http.get(
        f"/flows/api/v1/flows/{flow_id}/nodes/dst/code-agent",
        headers=headers,
        params={"branch_id": "default"},
    )
    assert dst_status.status_code == 200, dst_status.text
    paths = {item["relative_path"] for item in dst_status.json()["files"]}
    assert "main.py" in paths
    assert dst_status.json()["catalog_id"] != src_catalog
    deleted = await flows_client_http.delete(
        f"/flows/api/v1/flows/{flow_id}/nodes/src/code-agent",
        headers=headers,
        params={"branch_id": "default"},
    )
    assert deleted.status_code == 204, deleted.text


async def test_code_agent_rebuild_without_argv_400(
    flows_client_http: AsyncClient,
    office_service,
    guest_runtime_service,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    _ = office_service, guest_runtime_service
    require_s3_configured()
    headers = code_agent_headers(auth_headers_system)
    flow_id = f"ca_noargv_{unique_id}"
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
                }
            },
            "edges": [{"from_node": "agent", "to_node": None}],
        },
    )
    assert create.status_code == 200, create.text
    await ensure_code_agent_catalog(
        flows_client_http, headers, flow_id=flow_id, node_id="agent"
    )
    await upload_code_agent_file(
        flows_client_http,
        headers,
        flow_id=flow_id,
        node_id="agent",
        original_name="main.py",
        content=example_main_py_bytes(),
    )
    rebuilt = await flows_client_http.post(
        f"/flows/api/v1/flows/{flow_id}/nodes/agent/code-agent/rebuild",
        headers=headers,
        params={"branch_id": "default"},
        json={
            "language": "python",
            "invoke_kind": "cli",
            "invoke_argv": [],
        },
    )
    assert rebuilt.status_code == 400, rebuilt.text


async def test_code_agent_rebuild_denies_torch(
    flows_client_http: AsyncClient,
    office_service,
    guest_runtime_service,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    _ = office_service, guest_runtime_service
    require_s3_configured()
    headers = code_agent_headers(auth_headers_system)
    flow_id = f"ca_torch_{unique_id}"
    await _create_python_cli(flows_client_http, headers, flow_id=flow_id)
    await ensure_code_agent_catalog(
        flows_client_http, headers, flow_id=flow_id, node_id="agent"
    )
    await upload_code_agent_file(
        flows_client_http,
        headers,
        flow_id=flow_id,
        node_id="agent",
        original_name="main.py",
        content=example_main_py_bytes(),
    )
    await upload_code_agent_file(
        flows_client_http,
        headers,
        flow_id=flow_id,
        node_id="agent",
        original_name="requirements.txt",
        content=b"torch==2.0\n",
    )
    rebuilt = await flows_client_http.post(
        f"/flows/api/v1/flows/{flow_id}/nodes/agent/code-agent/rebuild",
        headers=headers,
        params={"branch_id": "default"},
        json={
            "language": "python",
            "invoke_kind": "cli",
            "invoke_argv": ["python", "main.py"],
        },
    )
    assert rebuilt.status_code == 400, rebuilt.text
    assert "torch" in rebuilt.text
