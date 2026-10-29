"""Каталоги кэша code runner из Settings."""

from __future__ import annotations

import contextlib
import fcntl
from collections.abc import Generator
from pathlib import Path

from core.config import get_settings


@contextlib.contextmanager
def sandbox_cache_lock(cache_root: Path) -> Generator[None, None, None]:
    """flock на соседнем lock-файле: один процесс пересобирает кэш, остальные ждут."""
    lock_path = cache_root.parent / f"{cache_root.name}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield


def code_runner_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def code_runner_lsp_cache_root() -> Path:
    """Корень кэша language server."""
    return _configured_dir(
        get_settings().code_runner.lsp_cache,
        code_runner_repo_root() / ".cache",
    )


def code_runner_python_sandbox_site() -> Path:
    """Target site-packages Python sandbox."""
    return _configured_dir(
        get_settings().code_runner.python_sandbox_site,
        code_runner_repo_root() / ".cache" / "code-runner-python-sandbox-site",
    )


def code_runner_node_sandbox_modules() -> Path:
    """Prefix npm-пакетов Node sandbox."""
    return _configured_dir(
        get_settings().code_runner.node_sandbox_modules,
        code_runner_repo_root() / ".cache" / "code-runner-node-sandbox-modules",
    )


def _configured_dir(value: str, default: Path) -> Path:
    configured = value.strip()
    if configured == "":
        return default
    return Path(configured)


__all__ = [
    "code_runner_lsp_cache_root",
    "code_runner_node_sandbox_modules",
    "code_runner_python_sandbox_site",
    "code_runner_repo_root",
    "sandbox_cache_lock",
]
