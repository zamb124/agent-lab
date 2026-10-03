"""Go language server command."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from core.capabilities.lsp_commands import run_exclusive_lsp_install
from core.capabilities.models import LspWorkspace
from core.capabilities.runner_cache import code_runner_lsp_cache_root
from core.capabilities.runtime_executables import (
    platform_runtime_bin_dir,
    resolve_runtime_executable,
    runtime_executable_required_message,
)
from core.utils.process_env import child_process_env


def go_lsp_command() -> list[str]:
    existing = shutil.which("gopls")
    if existing is not None:
        return [existing, "serve"]
    cache = code_runner_lsp_cache_root() / "code-runner-go-lsp"
    gobin = cache / "bin"
    binary = gobin / "gopls"

    def ready() -> bool:
        return binary.is_file()

    def install() -> None:
        if ready():
            return
        go_bin = resolve_runtime_executable("go")
        if go_bin is None:
            raise RuntimeError(runtime_executable_required_message("go"))
        gobin.mkdir(parents=True, exist_ok=True)
        env = child_process_env()
        env["PATH"] = f"{platform_runtime_bin_dir()}{os.pathsep}{env.get('PATH', '')}"
        env["GOBIN"] = str(gobin)
        completed = subprocess.run(
            [go_bin, "install", "golang.org/x/tools/gopls@latest"],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        if ready():
            return
        raise RuntimeError(f"gopls install failed: {completed.stderr}")

    run_exclusive_lsp_install(
        ready=ready,
        install=install,
        lock_dir=cache.parent / f".{cache.name}.install-lock",
    )
    if not binary.is_file():
        raise RuntimeError("gopls is required for go code_node LSP")
    return [str(binary), "serve"]


def prepare_go_lsp_workspace(root: Path, workspace: LspWorkspace) -> None:
    _ = root, workspace
