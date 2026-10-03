from __future__ import annotations

import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from core.capabilities.runtime_executables import (
    resolve_runtime_executable,
    runtime_executable_required_message,
)
from core.config import get_settings
from core.config.base import BaseSettings


@contextmanager
def _runtime_lookup(
    *,
    runtime_dir: str,
    path: str,
    go_bin: str = "",
    node_bin: str = "",
) -> Iterator[None]:
    settings = get_settings().code_runner
    previous = (
        settings.runtime_dir,
        settings.go_bin,
        settings.node_bin,
        settings.npm_bin,
        settings.dotnet_bin,
    )
    previous_path = os.environ.get("PATH")
    settings.runtime_dir = runtime_dir
    settings.go_bin = go_bin
    settings.node_bin = node_bin
    settings.npm_bin = ""
    settings.dotnet_bin = ""
    os.environ["PATH"] = path
    try:
        yield
    finally:
        (
            settings.runtime_dir,
            settings.go_bin,
            settings.node_bin,
            settings.npm_bin,
            settings.dotnet_bin,
        ) = previous
        if previous_path is None:
            os.environ.pop("PATH", None)
        else:
            os.environ["PATH"] = previous_path


def _make_executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def test_runtime_dir_reads_nested_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODE_RUNNER__RUNTIME_DIR", "/tmp/platform-runtimes")
    assert BaseSettings().code_runner.runtime_dir == "/tmp/platform-runtimes"


def test_resolves_managed_runtime_bin_without_path(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtimes"
    go_bin = _make_executable(runtime_dir / "bin" / "go")

    with _runtime_lookup(runtime_dir=str(runtime_dir), path=""):
        assert resolve_runtime_executable("go") == str(go_bin)


def test_explicit_runtime_override_wins_over_managed_runtime(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtimes"
    _ = _make_executable(runtime_dir / "bin" / "go")
    override = _make_executable(tmp_path / "custom" / "go")

    with _runtime_lookup(runtime_dir=str(runtime_dir), path="", go_bin=str(override)):
        assert resolve_runtime_executable("go") == str(override)


def test_invalid_explicit_runtime_override_is_not_silently_replaced(
    tmp_path: Path,
) -> None:
    runtime_dir = tmp_path / "runtimes"
    _ = _make_executable(runtime_dir / "bin" / "go")

    with _runtime_lookup(
        runtime_dir=str(runtime_dir),
        path="",
        go_bin=str(tmp_path / "missing-go"),
    ):
        assert resolve_runtime_executable("go") is None


def test_resolves_path_runtime_when_managed_runtime_is_absent(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtimes"
    path_bin = tmp_path / "path-bin"
    node_bin = _make_executable(path_bin / "node")

    with _runtime_lookup(runtime_dir=str(runtime_dir), path=str(path_bin)):
        assert resolve_runtime_executable("node") == str(node_bin)


def test_missing_runtime_message_lists_canonical_sources(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtimes"

    with _runtime_lookup(runtime_dir=str(runtime_dir), path=""):
        message = runtime_executable_required_message("go")

    assert "go executable is required" in message
    assert "code_runner.runtime_dir/bin/go" in message
    assert "PATH:go" in message
    assert "code_runner.go_bin" in message
