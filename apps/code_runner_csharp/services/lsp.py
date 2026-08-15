"""C# language server command and vfs restore."""

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
DOTNET_BIN_ENV = "CODE_RUNNER_DOTNET_BIN"


def csharp_lsp_command() -> list[str]:
    existing = shutil.which("csharp-ls")
    if existing is not None:
        return [existing]
    cache = (
        Path(
            os.environ["CODE_RUNNER_LSP_CACHE"]
            if "CODE_RUNNER_LSP_CACHE" in os.environ
            else str(_REPO_ROOT / ".cache")
        )
        / "code-runner-csharp-lsp"
    )
    binary = cache / "csharp-ls"

    def ready() -> bool:
        return binary.is_file()

    def install() -> None:
        if ready():
            return
        dotnet = resolve_runtime_executable("dotnet", override_env=DOTNET_BIN_ENV)
        if dotnet is None:
            raise RuntimeError(
                runtime_executable_required_message("dotnet", override_env=DOTNET_BIN_ENV)
            )
        cache.mkdir(parents=True, exist_ok=True)
        env = _dotnet_env(dotnet)
        completed = subprocess.run(
            [dotnet, "tool", "install", "csharp-ls", "--tool-path", str(cache)],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        if ready():
            return
        raise RuntimeError(f"csharp-ls install failed: {completed.stderr}")

    run_exclusive_lsp_install(
        ready=ready,
        install=install,
        lock_dir=cache.parent / f".{cache.name}.install-lock",
    )
    if not binary.is_file():
        raise RuntimeError("csharp-ls is required for csharp code_node LSP")
    return [str(binary)]


def prepare_csharp_lsp_workspace(root: Path, workspace: LspWorkspace) -> None:
    _ = workspace
    dotnet = resolve_runtime_executable("dotnet", override_env=DOTNET_BIN_ENV)
    if dotnet is None:
        raise RuntimeError(
            runtime_executable_required_message("dotnet", override_env=DOTNET_BIN_ENV)
        )
    completed = subprocess.run(
        [dotnet, "restore", "--nologo"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        env=_dotnet_env(dotnet),
    )
    if completed.returncode != 0:
        raise RuntimeError(f"csharp LSP restore failed: {completed.stderr}")


def _dotnet_env(dotnet: str) -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = f"{platform_runtime_bin_dir()}{os.pathsep}{env.get('PATH', '')}"
    env["DOTNET_ROOT"] = str(Path(dotnet).resolve().parent)
    return env
