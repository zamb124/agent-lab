"""C# language server command and vfs restore."""

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


def csharp_lsp_command() -> list[str]:
    existing = shutil.which("csharp-ls")
    if existing is not None:
        return [existing]
    cache = code_runner_lsp_cache_root() / "code-runner-csharp-lsp"
    binary = cache / "csharp-ls"

    def ready() -> bool:
        return binary.is_file()

    def install() -> None:
        if ready():
            return
        dotnet = resolve_runtime_executable("dotnet")
        if dotnet is None:
            raise RuntimeError(
                runtime_executable_required_message("dotnet")
            )
        cache.mkdir(parents=True, exist_ok=True)
        env = _dotnet_env(dotnet)
        completed = subprocess.run(
            [
                dotnet,
                "tool",
                "install",
                "csharp-ls",
                "--version",
                "0.28.0",
                "--tool-path",
                str(cache),
            ],
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
    dotnet = resolve_runtime_executable("dotnet")
    if dotnet is None:
        raise RuntimeError(
            runtime_executable_required_message("dotnet")
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
    env = child_process_env()
    env["PATH"] = f"{platform_runtime_bin_dir()}{os.pathsep}{env.get('PATH', '')}"
    env["DOTNET_ROOT"] = str(Path(dotnet).resolve().parent)
    return env
