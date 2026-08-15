"""Node language server command and vfs prepare."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

from apps.code_runner_node.services.executor import NODE_BIN_ENV, ensure_node_sandbox_modules
from core.capabilities.lsp_commands import run_exclusive_lsp_install
from core.capabilities.models import LspWorkspace
from core.capabilities.runtime_executables import (
    platform_runtime_bin_dir,
    resolve_runtime_executable,
    runtime_executable_required_message,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_LSP_PACKAGE_JSON = Path(__file__).resolve().parents[1] / "lsp_modules" / "package.json"


def node_lsp_command() -> list[str]:
    cache = _ensure_node_lsp_modules()
    binary = cache / "node_modules" / ".bin" / "typescript-language-server"
    if resolve_runtime_executable("node", override_env=NODE_BIN_ENV) is None:
        raise RuntimeError(runtime_executable_required_message("node", override_env=NODE_BIN_ENV))
    if not binary.is_file():
        raise RuntimeError(
            "typescript-language-server is required for javascript/typescript code_node LSP"
        )
    return [str(binary), "--stdio"]


def prepare_node_lsp_workspace(root: Path, workspace: LspWorkspace) -> None:
    _ = workspace
    sandbox = ensure_node_sandbox_modules()
    link = root / "node_modules"
    if link.exists() or link.is_symlink():
        link.unlink()
    link.symlink_to(sandbox / "node_modules", target_is_directory=True)


def _ensure_node_lsp_modules() -> Path:
    cache = (
        Path(
            os.environ["CODE_RUNNER_LSP_CACHE"]
            if "CODE_RUNNER_LSP_CACHE" in os.environ
            else str(_REPO_ROOT / ".cache")
        )
        / "code-runner-node-lsp-modules"
    )
    digest = hashlib.sha256(_LSP_PACKAGE_JSON.read_bytes()).hexdigest()
    marker = cache / ".package.sha256"
    binary = cache / "node_modules" / ".bin" / "typescript-language-server"

    def ready() -> bool:
        return (
            marker.is_file()
            and marker.read_text(encoding="utf-8").strip() == digest
            and binary.is_file()
        )

    def install() -> None:
        if ready():
            return
        if cache.exists():
            shutil.rmtree(cache)
        cache.mkdir(parents=True, exist_ok=True)
        _ = (cache / "package.json").write_bytes(_LSP_PACKAGE_JSON.read_bytes())
        npm_bin = resolve_runtime_executable("npm", override_env="CODE_RUNNER_NPM_BIN")
        if npm_bin is None:
            raise RuntimeError(
                runtime_executable_required_message("npm", override_env="CODE_RUNNER_NPM_BIN")
            )
        env = os.environ.copy()
        env["PATH"] = f"{platform_runtime_bin_dir()}{os.pathsep}{env.get('PATH', '')}"
        completed = subprocess.run(
            [npm_bin, "install", "--omit=dev"],
            cwd=cache,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        if not binary.is_file():
            raise RuntimeError(f"typescript-language-server install failed: {completed.stderr}")
        _ = marker.write_text(digest, encoding="utf-8")

    run_exclusive_lsp_install(
        ready=ready,
        install=install,
        lock_dir=cache.parent / f".{cache.name}.install-lock",
    )
    if not ready():
        raise RuntimeError(
            "typescript-language-server is required for javascript/typescript code_node LSP"
        )
    return cache
