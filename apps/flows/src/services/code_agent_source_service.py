"""Исходники code_agent: каталог Documents, ingest git/zip, rebuild на ферме."""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

from apps.flows.src.db import FlowRepository
from apps.flows.src.models.flow_config import FlowConfig
from core.clients.documents_client import DocumentsClient
from core.clients.files_client import FilesClient
from core.clients.guest_runtime_client import GuestRuntimeClient
from core.config import get_settings
from core.context import require_active_company, require_context
from core.documents.placement import DocsPlacementAnchor
from core.documents.placement_paths import build_path_segments
from core.files.create_spec import FileCreateSpec, FileSourceKind, FileSourceRef
from core.files.registry import default_retention_for_source
from core.files.service import FilesService
from core.files.types import ext_to_mime
from core.guest_runtime.git_url import (
    normalize_code_agent_git_remote,
    parse_ls_remote_head,
    resolve_code_agent_source_sha,
)
from core.guest_runtime.models import (
    CodeAgentEnsureSourceResponse,
    CodeAgentNodeStatusResponse,
    CodeAgentRebuildRequest,
    CodeAgentSourceFile,
    GuestBuildStatus,
    GuestRebuildRequest,
    GuestRebuildResponse,
    GuestRuntimeLogsResponse,
)
from core.guest_runtime.source_budget import (
    assert_code_agent_source_upload_fits,
    assert_source_bytes_within_cap,
)
from core.guest_runtime.source_tree import walk_code_agent_catalog
from core.types import JsonObject, require_json_object


class CodeAgentSourceService:
    def __init__(
        self,
        *,
        flow_repository: FlowRepository,
        files_service: FilesService,
        files_client: FilesClient,
        documents_client: DocumentsClient,
        guest_runtime_client: GuestRuntimeClient,
    ) -> None:
        self._flows: FlowRepository = flow_repository
        self._files: FilesService = files_service
        self._file_bytes: FilesClient = files_client
        self._documents: DocumentsClient = documents_client
        self._farm: GuestRuntimeClient = guest_runtime_client

    async def ensure_source(
        self, *, flow_id: str, node_id: str, branch_id: str
    ) -> CodeAgentEnsureSourceResponse:
        return await self._ensure_catalog(
            flow_id=flow_id, node_id=node_id, branch_id=branch_id
        )

    async def import_git(
        self,
        *,
        flow_id: str,
        node_id: str,
        branch_id: str,
        git_url: str,
        source_sha: str,
    ) -> CodeAgentNodeStatusResponse:
        if not git_url.strip():
            raise ValueError("git_url required")
        resolved_sha = resolve_code_agent_source_sha(
            git_url=git_url, source_sha=source_sha
        )
        git = shutil.which("git")
        if git is None:
            raise RuntimeError("git is required for code_agent import-git")
        dest = Path(tempfile.mkdtemp(prefix="code-agent-git-"))
        env = dict(os.environ)
        env["GIT_TERMINAL_PROMPT"] = "0"
        remote_url = normalize_code_agent_git_remote(git_url)
        try:
            if resolved_sha == "":
                ls_out = await self._run_cmd_output(
                    [git, "ls-remote", remote_url, "HEAD"], cwd=dest, env=env
                )
                resolved_sha = parse_ls_remote_head(ls_out, remote_url=remote_url)
            await self._run_cmd([git, "init"], cwd=dest, env=env)
            await self._run_cmd(
                [git, "remote", "add", "origin", remote_url], cwd=dest, env=env
            )
            await self._run_cmd(
                [git, "fetch", "--depth", "1", "origin", resolved_sha],
                cwd=dest,
                env=env,
            )
            await self._run_cmd(
                [git, "checkout", "--force", "FETCH_HEAD"], cwd=dest, env=env
            )
            await self._replace_tree_from_directory(
                flow_id=flow_id,
                node_id=node_id,
                branch_id=branch_id,
                root=dest,
                skip_names={".git"},
            )
        finally:
            shutil.rmtree(dest, ignore_errors=False)
        await self._patch_node_if_present(
            await self._require_flow(flow_id),
            node_id=node_id,
            branch_id=branch_id,
            fields={"git_url": git_url.strip(), "source_sha": resolved_sha},
        )
        source = await self._source_status(
            flow_id=flow_id, node_id=node_id, branch_id=branch_id
        )
        return source.model_copy(
            update={"git_url": git_url.strip(), "source_sha": resolved_sha}
        )

    async def import_archive(
        self,
        *,
        flow_id: str,
        node_id: str,
        branch_id: str,
        file_id: str,
    ) -> CodeAgentNodeStatusResponse:
        payload = await self._file_bytes.get_bytes(file_id)
        dest = Path(tempfile.mkdtemp(prefix="code-agent-zip-"))
        archive_path = dest / "source.zip"
        try:
            _ = archive_path.write_bytes(payload)
            with zipfile.ZipFile(archive_path) as archive:
                archive.extractall(dest / "unpacked")
            unpacked = dest / "unpacked"
            await self._replace_tree_from_directory(
                flow_id=flow_id,
                node_id=node_id,
                branch_id=branch_id,
                root=unpacked,
                skip_names={"__MACOSX"},
            )
        finally:
            shutil.rmtree(dest, ignore_errors=False)
        return await self._source_status(
            flow_id=flow_id, node_id=node_id, branch_id=branch_id
        )

    async def copy_tree(
        self,
        *,
        flow_id: str,
        node_id: str,
        branch_id: str,
        from_catalog_id: str,
    ) -> CodeAgentEnsureSourceResponse:
        ensured = await self.ensure_source(
            flow_id=flow_id, node_id=node_id, branch_id=branch_id
        )
        source_files = await walk_code_agent_catalog(self._documents, from_catalog_id)
        dest_files = await walk_code_agent_catalog(self._documents, ensured.catalog_id)
        assert_source_bytes_within_cap(
            existing_bytes=sum(item.file_size for item in dest_files),
            incoming_bytes=sum(item.file_size for item in source_files),
            max_bytes=get_settings().guest_runtime.max_source_bytes,
        )
        for item in source_files:
            parent, filename = _split_relative_path(item.relative_path)
            data = await self._file_bytes.get_bytes(item.file_id)
            await self._create_source_file(
                flow_id=flow_id,
                node_id=node_id,
                relative_dir=parent,
                filename=filename,
                data=data,
            )
        return ensured

    async def list_files(self, *, catalog_id: str) -> list[CodeAgentSourceFile]:
        if not catalog_id.strip():
            raise ValueError("catalog_id required")
        return await walk_code_agent_catalog(self._documents, catalog_id.strip())

    async def status(
        self, *, flow_id: str, node_id: str, branch_id: str
    ) -> CodeAgentNodeStatusResponse:
        source = await self._source_status(
            flow_id=flow_id, node_id=node_id, branch_id=branch_id
        )
        farm_status = await self._farm.status(flow_id, node_id)
        runtime = farm_status.runtime
        if runtime is None:
            return source
        return source.model_copy(
            update={
                "image_digest": runtime.image_digest,
                "build_status": runtime.build_status,
                "build_error": runtime.build_error,
            }
        )

    async def _source_status(
        self, *, flow_id: str, node_id: str, branch_id: str
    ) -> CodeAgentNodeStatusResponse:
        ensured = await self._ensure_catalog(
            flow_id=flow_id, node_id=node_id, branch_id=branch_id
        )
        node = await self._find_node(flow_id, node_id, branch_id)
        files = await self.list_files(catalog_id=ensured.catalog_id)
        return CodeAgentNodeStatusResponse(
            catalog_id=ensured.catalog_id,
            git_url=_node_string(node, "git_url") if node is not None else None,
            source_sha=_node_string(node, "source_sha") if node is not None else None,
            image_digest=None,
            build_status=GuestBuildStatus.NONE,
            build_error=None,
            files=files,
        )

    async def rebuild(
        self,
        *,
        flow_id: str,
        node_id: str,
        branch_id: str,
        request: CodeAgentRebuildRequest,
    ) -> GuestRebuildResponse:
        ctx = require_context()
        company = require_active_company()
        if not request.invoke_argv:
            raise ValueError("code_agent invoke_argv is required at rebuild")
        for item in request.invoke_argv:
            if item.strip() == "":
                raise ValueError("code_agent invoke_argv items must be non-empty")
        ensured = await self._ensure_catalog(
            flow_id=flow_id, node_id=node_id, branch_id=branch_id
        )
        files = await self.list_files(catalog_id=ensured.catalog_id)
        return await self._farm.rebuild(
            GuestRebuildRequest(
                flow_id=flow_id,
                node_id=node_id,
                company_id=company.company_id,
                user_id=ctx.user.user_id,
                catalog_id=ensured.catalog_id,
                language=request.language,
                invoke_kind=request.invoke_kind,
                invoke_argv=request.invoke_argv,
                invoke_listen_port=request.invoke_listen_port,
                egress_hosts=request.egress_hosts,
                files=files,
                git_url=request.git_url,
                source_sha=request.source_sha,
            )
        )

    async def logs(
        self,
        *,
        flow_id: str,
        node_id: str,
        task_id: str | None = None,
        session_id: str | None = None,
        context_id: str | None = None,
    ) -> GuestRuntimeLogsResponse:
        return await self._farm.logs(
            flow_id,
            node_id,
            task_id=task_id,
            session_id=session_id,
            context_id=context_id,
        )

    async def delete_source(
        self,
        *,
        flow_id: str,
        node_id: str,
        branch_id: str,
        catalog_id: str | None = None,
    ) -> None:
        node = await self._find_node(flow_id, node_id, branch_id)
        resolved_catalog_id = catalog_id.strip() if catalog_id is not None and catalog_id.strip() else None
        if resolved_catalog_id is None and node is not None:
            resolved_catalog_id = _node_string(node, "catalog_id")
        if resolved_catalog_id is not None:
            await self._delete_catalog_tree(resolved_catalog_id)
        await self._farm.drop(flow_id, node_id)
        flow = await self._require_flow(flow_id)
        await self._patch_node_if_present(
            flow,
            node_id=node_id,
            branch_id=branch_id,
            fields={"catalog_id": None},
        )

    async def _replace_tree_from_directory(
        self,
        *,
        flow_id: str,
        node_id: str,
        branch_id: str,
        root: Path,
        skip_names: set[str],
    ) -> None:
        ensured = await self.ensure_source(
            flow_id=flow_id, node_id=node_id, branch_id=branch_id
        )
        existing = await walk_code_agent_catalog(self._documents, ensured.catalog_id)
        for item in existing:
            _ = await self._documents.delete(item.file_id)
        max_bytes = get_settings().guest_runtime.max_source_bytes
        total = 0
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            parts = rel.split("/")
            if any(part in skip_names for part in parts):
                continue
            if any(part in {".", ".."} for part in parts):
                raise ValueError(f"invalid relative path: {rel}")
            data = path.read_bytes()
            if len(data) == 0:
                continue
            total += len(data)
            if total > max_bytes:
                raise ValueError(
                    f"code_agent source exceeds {max_bytes} bytes: {total}"
                )
            parent, filename = _split_relative_path(rel)
            await self._create_source_file(
                flow_id=flow_id,
                node_id=node_id,
                relative_dir=parent,
                filename=filename,
                data=data,
            )

    async def _create_source_file(
        self,
        *,
        flow_id: str,
        node_id: str,
        relative_dir: str | None,
        filename: str,
        data: bytes,
    ) -> None:
        spec = FileCreateSpec(
            source_kind=FileSourceKind.CODE_AGENT_SOURCE,
            source_ref=FileSourceRef(
                flow_id=flow_id,
                node_id=node_id,
                relative_dir=relative_dir,
            ),
            retention=default_retention_for_source(FileSourceKind.CODE_AGENT_SOURCE),
        )
        await assert_code_agent_source_upload_fits(spec, incoming_bytes=len(data))
        suffix = Path(filename).suffix.lower()
        _ = await self._files.create(
            spec,
            data,
            original_name=filename,
            content_type=ext_to_mime(suffix),
        )

    async def _delete_catalog_tree(self, catalog_id: str) -> None:
        payload = await self._documents.list_catalog_items(catalog_id)
        documents = payload.get("documents")
        catalogs = payload.get("catalogs")
        if not isinstance(documents, list) or not isinstance(catalogs, list):
            raise ValueError("catalog items required")
        for raw_doc in documents:
            document = require_json_object(raw_doc, "catalog.documents[]")
            file_id = document.get("file_id")
            if not isinstance(file_id, str) or file_id.strip() == "":
                raise ValueError("document file_id required")
            _ = await self._documents.delete(file_id)
        for raw_catalog in catalogs:
            catalog = require_json_object(raw_catalog, "catalog.catalogs[]")
            child_id = catalog.get("catalog_id")
            if not isinstance(child_id, str) or child_id.strip() == "":
                raise ValueError("child catalog_id required")
            await self._delete_catalog_tree(child_id)
        await self._documents.delete_catalog(catalog_id)

    async def _ensure_catalog(
        self, *, flow_id: str, node_id: str, branch_id: str
    ) -> CodeAgentEnsureSourceResponse:
        _ = require_context()
        _ = require_active_company()
        flow = await self._require_flow(flow_id)
        segments = build_path_segments(
            DocsPlacementAnchor(
                source_kind="code_agent_source",
                flow_id=flow_id,
                flow_slug=flow.flow_id,
                node_id=node_id,
            )
        )
        ensured = await self._documents.ensure_catalog_path(segments)
        # Дерево исходников создаётся и до сохранения ноды в графе (редактор ещё не нажал
        # «сохранить»): catalog_id закрепляем на ноде только когда она уже в конфиге.
        node = await self._find_node(flow_id, node_id, branch_id)
        if node is not None and _node_string(node, "catalog_id") != ensured.catalog_id:
            await self._patch_node(
                flow,
                node_id=node_id,
                branch_id=branch_id,
                fields={"catalog_id": ensured.catalog_id},
            )
        return CodeAgentEnsureSourceResponse(
            catalog_id=ensured.catalog_id,
            flow_id=flow_id,
            node_id=node_id,
            catalog_path=ensured.catalog_path,
        )

    async def _require_flow(self, flow_id: str) -> FlowConfig:
        flow = await self._flows.get(flow_id)
        if flow is None:
            raise LookupError(f"flow not found: {flow_id}")
        return flow

    async def _find_node(
        self, flow_id: str, node_id: str, branch_id: str
    ) -> JsonObject | None:
        flow = await self._require_flow(flow_id)
        resolved_branch = "default" if branch_id in {"", "base"} else branch_id
        if resolved_branch == "default" and flow.nodes is not None:
            raw = flow.nodes.get(node_id)
            if isinstance(raw, dict):
                return require_json_object(raw, "flow.nodes")
        branch = flow.branches.get(resolved_branch)
        if branch is not None and branch.nodes is not None:
            raw = branch.nodes.get(node_id)
            if isinstance(raw, dict):
                return require_json_object(raw, "branch.nodes")
        if flow.nodes is not None:
            raw = flow.nodes.get(node_id)
            if isinstance(raw, dict):
                return require_json_object(raw, "flow.nodes")
        return None

    async def _patch_node(
        self,
        flow: FlowConfig,
        *,
        node_id: str,
        branch_id: str,
        fields: JsonObject,
    ) -> None:
        resolved_branch = "default" if branch_id in {"", "base"} else branch_id
        updated = False
        if flow.nodes is not None and node_id in flow.nodes:
            current = dict(flow.nodes[node_id])
            current.update(fields)
            nodes = dict(flow.nodes)
            nodes[node_id] = current
            flow.nodes = nodes
            updated = True
        branch = flow.branches.get(resolved_branch)
        if branch is not None and branch.nodes is not None and node_id in branch.nodes:
            current = dict(branch.nodes[node_id])
            current.update(fields)
            branch.nodes[node_id] = current
            updated = True
        if not updated:
            raise LookupError(f"code_agent node not found: {node_id}")
        saved = await self._flows.set(flow)
        if not saved:
            raise RuntimeError("failed to persist flow after code_agent source update")

    async def _patch_node_if_present(
        self,
        flow: FlowConfig,
        *,
        node_id: str,
        branch_id: str,
        fields: JsonObject,
    ) -> None:
        if await self._find_node(flow.flow_id, node_id, branch_id) is None:
            return
        await self._patch_node(
            flow,
            node_id=node_id,
            branch_id=branch_id,
            fields=fields,
        )

    async def _run_cmd(
        self, argv: list[str], *, cwd: Path, env: dict[str, str]
    ) -> None:
        _ = await self._run_cmd_output(argv, cwd=cwd, env=env)

    async def _run_cmd_output(
        self, argv: list[str], *, cwd: Path, env: dict[str, str]
    ) -> str:
        process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(cwd),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await process.communicate()
        stdout_text = out.decode("utf-8", errors="replace")
        stderr_text = err.decode("utf-8", errors="replace")
        if process.returncode != 0:
            raise RuntimeError(f"{argv[0]} failed: {stdout_text}{stderr_text}")
        return stdout_text


def _split_relative_path(relative_path: str) -> tuple[str | None, str]:
    parts = relative_path.split("/")
    filename = parts[-1]
    if filename.strip() == "":
        raise ValueError("relative_path must include a filename")
    parent = "/".join(parts[:-1])
    return (parent if parent else None, filename)


def _node_string(node: JsonObject, field: str) -> str | None:
    value = node.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field}: expected string")
    stripped = value.strip()
    return stripped if stripped else None
