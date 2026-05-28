"""Разрешение managed runtime executables для sandbox runners."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

PLATFORM_RUNTIME_DIR_ENV = "PLATFORM_RUNTIME_DIR"
DEFAULT_PLATFORM_RUNTIME_DIR = "~/.cache/agent-lab/runtimes"


@dataclass(frozen=True)
class RuntimeExecutableResolution:
    executable: str | None
    checked: tuple[str, ...]


def platform_runtime_dir() -> Path:
    return Path(
        os.environ.get(PLATFORM_RUNTIME_DIR_ENV, DEFAULT_PLATFORM_RUNTIME_DIR)
    ).expanduser()


def platform_runtime_bin_dir() -> Path:
    return platform_runtime_dir() / "bin"


def resolve_runtime_executable(
    executable_name: str,
    *,
    override_env: str,
) -> str | None:
    return resolve_runtime_executable_with_details(
        executable_name,
        override_env=override_env,
    ).executable


def resolve_runtime_executable_with_details(
    executable_name: str,
    *,
    override_env: str,
) -> RuntimeExecutableResolution:
    checked: list[str] = []

    override = os.environ.get(override_env)
    if override:
        checked.append(f"${override_env}={override}")
        resolved = _resolve_candidate(override)
        return RuntimeExecutableResolution(executable=resolved, checked=tuple(checked))

    managed_path = platform_runtime_bin_dir() / executable_name
    checked.append(f"${PLATFORM_RUNTIME_DIR_ENV}/bin/{executable_name}={managed_path}")
    if _is_executable(managed_path):
        return RuntimeExecutableResolution(
            executable=str(managed_path),
            checked=tuple(checked),
        )

    checked.append(f"PATH:{executable_name}")
    return RuntimeExecutableResolution(
        executable=shutil.which(executable_name),
        checked=tuple(checked),
    )


def runtime_executable_required_message(
    executable_name: str,
    *,
    override_env: str,
) -> str:
    resolution = resolve_runtime_executable_with_details(
        executable_name,
        override_env=override_env,
    )
    checked = "; ".join(resolution.checked)
    return (
        f"{executable_name} executable is required; checked {checked}. "
        f"Run `make bootstrap-runtimes` or set ${override_env}."
    )


def _resolve_candidate(candidate: str) -> str | None:
    if _candidate_is_path(candidate):
        path = Path(candidate).expanduser()
        return str(path) if _is_executable(path) else None
    return shutil.which(candidate)


def _candidate_is_path(candidate: str) -> bool:
    if os.sep in candidate:
        return True
    return os.altsep is not None and os.altsep in candidate


def _is_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)
