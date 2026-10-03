"""Интерпретатор и language server Python без platform site-packages."""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from core.capabilities.runner_cache import code_runner_lsp_cache_root


def run_exclusive_lsp_install(
    *,
    ready: Callable[[], bool],
    install: Callable[[], None],
    lock_dir: Path,
    timeout_seconds: float = 180.0,
) -> None:
    """Один writer на cache-директорию: параллельный first-install под xdist не rmtree чужой бинарь."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if ready():
            return
        try:
            lock_dir.mkdir(parents=True)
        except FileExistsError:
            _clear_stale_lsp_install_lock(lock_dir, timeout_seconds)
            time.sleep(0.25)
            continue
        except FileNotFoundError:
            lock_dir.parent.mkdir(parents=True, exist_ok=True)
            continue
        try:
            if ready():
                return
            install()
            if not ready():
                raise RuntimeError(
                    f"LSP toolchain install did not produce artifacts for {lock_dir}"
                )
            return
        finally:
            if lock_dir.exists():
                shutil.rmtree(lock_dir)
    raise RuntimeError(f"timed out installing LSP toolchain ({lock_dir})")


def _clear_stale_lsp_install_lock(lock_dir: Path, timeout_seconds: float) -> None:
    if not lock_dir.exists():
        return
    age_seconds = time.time() - lock_dir.stat().st_mtime
    if age_seconds > timeout_seconds:
        shutil.rmtree(lock_dir)


def python_lsp_interpreter() -> Path:
    """Пустой venv + basedpyright: `import apps` / `import core` не резолвятся."""
    cache = _cache_dir("code-runner-python-lsp-venv")
    python_bin = cache / "bin" / "python"
    langserver = cache / "bin" / "basedpyright-langserver"
    marker = cache / ".venv.ok"

    def ready() -> bool:
        return python_bin.is_file() and langserver.is_file() and marker.is_file()

    def install() -> None:
        if ready():
            return
        if cache.exists():
            shutil.rmtree(cache)
        uv_bin = shutil.which("uv")
        if uv_bin is None:
            raise RuntimeError("uv is required to create the python LSP interpreter")
        venv_completed = subprocess.run(
            [uv_bin, "venv", str(cache), "--python", sys.executable],
            check=False,
            capture_output=True,
            text=True,
        )
        if venv_completed.returncode != 0 or not python_bin.is_file():
            raise RuntimeError(f"python LSP venv failed: {venv_completed.stderr}")
        pip_completed = subprocess.run(
            [uv_bin, "pip", "install", "--python", str(python_bin), "basedpyright>=1.39.4"],
            check=False,
            capture_output=True,
            text=True,
        )
        if pip_completed.returncode != 0 or not langserver.is_file():
            raise RuntimeError(f"python LSP basedpyright install failed: {pip_completed.stderr}")
        _ = marker.write_text("ok", encoding="utf-8")

    run_exclusive_lsp_install(
        ready=ready,
        install=install,
        lock_dir=cache.parent / f".{cache.name}.install-lock",
    )
    if not ready():
        raise RuntimeError("python LSP interpreter is required")
    return python_bin


def python_lsp_command() -> list[str]:
    interpreter = python_lsp_interpreter()
    binary = interpreter.parent / "basedpyright-langserver"
    if not binary.is_file():
        raise RuntimeError("basedpyright-langserver is required for python code_node LSP")
    return [str(binary), "--stdio"]


def _cache_dir(name: str) -> Path:
    return code_runner_lsp_cache_root() / name
