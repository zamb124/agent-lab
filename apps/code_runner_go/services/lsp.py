"""Go language server command."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from core.capabilities.lsp_commands import run_exclusive_lsp_install
from core.capabilities.models import LspWorkspace
from core.capabilities.runtime_executables import (
    platform_runtime_bin_dir,
    resolve_runtime_executable,
    runtime_executable_required_message,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
GO_BIN_ENV = "CODE_RUNNER_GO_BIN"


def go_lsp_command() -> list[str]:
    existing = shutil.which("gopls")
    if existing is not None:
        return [existing, "serve"]
    cache = (
        Path(
            os.environ["CODE_RUNNER_LSP_CACHE"]
            if "CODE_RUNNER_LSP_CACHE" in os.environ
            else str(_REPO_ROOT / ".cache")
        )
        / "code-runner-go-lsp"
    )
    gobin = cache / "bin"
    binary = gobin / "gopls"

    def ready() -> bool:
        return binary.is_file()

    def install() -> None:
        if ready():
            return
        go_bin = resolve_runtime_executable("go", override_env=GO_BIN_ENV)
        if go_bin is None:
            raise RuntimeError(runtime_executable_required_message("go", override_env=GO_BIN_ENV))
        gobin.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
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
