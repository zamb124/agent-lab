"""Разрешение managed runtime executables для sandbox runners."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from core.config import get_settings

_DEFAULT_RUNTIME_DIR = "~/.cache/agent-lab/runtimes"


@dataclass(frozen=True)
class RuntimeExecutableResolution:
    executable: str | None
    checked: tuple[str, ...]


def platform_runtime_dir() -> Path:
    configured = get_settings().code_runner.runtime_dir.strip()
    if configured == "":
        return Path(_DEFAULT_RUNTIME_DIR).expanduser()
    return Path(configured).expanduser()


def platform_runtime_bin_dir() -> Path:
    return platform_runtime_dir() / "bin"


def resolve_runtime_executable(executable_name: str) -> str | None:
    return resolve_runtime_executable_with_details(executable_name).executable


def resolve_runtime_executable_with_details(
    executable_name: str,
) -> RuntimeExecutableResolution:
    checked: list[str] = []
    field_name, override = _bin_override(executable_name)
    if override != "":
        checked.append(f"code_runner.{field_name}={override}")
        resolved = _resolve_candidate(override)
        return RuntimeExecutableResolution(executable=resolved, checked=tuple(checked))

    managed_path = platform_runtime_bin_dir() / executable_name
    checked.append(f"code_runner.runtime_dir/bin/{executable_name}={managed_path}")
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


def runtime_executable_required_message(executable_name: str) -> str:
    resolution = resolve_runtime_executable_with_details(executable_name)
    field_name, _override = _bin_override(executable_name)
    checked = "; ".join(resolution.checked)
    return (
        f"{executable_name} executable is required; checked {checked}. "
        f"Run `make bootstrap-runtimes` or set code_runner.{field_name}."
    )


def _bin_override(executable_name: str) -> tuple[str, str]:
    settings = get_settings().code_runner
    match executable_name:
        case "go":
            field_name = "go_bin"
            raw = settings.go_bin
        case "node":
            field_name = "node_bin"
            raw = settings.node_bin
        case "npm":
            field_name = "npm_bin"
            raw = settings.npm_bin
        case "dotnet":
            field_name = "dotnet_bin"
            raw = settings.dotnet_bin
        case _:
            raise ValueError(f"unknown runtime executable {executable_name}")
    return field_name, raw.strip()


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
