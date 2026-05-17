from __future__ import annotations

import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from core.capabilities.runtime_executables import (
    resolve_runtime_executable,
    runtime_executable_required_message,
)


@contextmanager
def _temporary_env(values: dict[str, str | None]) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _make_executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def test_resolves_managed_runtime_bin_without_path(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtimes"
    go_bin = _make_executable(runtime_dir / "bin" / "go")

    with _temporary_env(
        {
            "PLATFORM_RUNTIME_DIR": str(runtime_dir),
            "CODE_RUNNER_GO_BIN": None,
            "PATH": "",
        }
    ):
        assert resolve_runtime_executable("go", override_env="CODE_RUNNER_GO_BIN") == str(
            go_bin
        )


def test_explicit_runtime_override_wins_over_managed_runtime(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtimes"
    _ = _make_executable(runtime_dir / "bin" / "go")
    override = _make_executable(tmp_path / "custom" / "go")

    with _temporary_env(
        {
            "PLATFORM_RUNTIME_DIR": str(runtime_dir),
            "CODE_RUNNER_GO_BIN": str(override),
            "PATH": "",
        }
    ):
        assert resolve_runtime_executable("go", override_env="CODE_RUNNER_GO_BIN") == str(
            override
        )


def test_invalid_explicit_runtime_override_is_not_silently_replaced(
    tmp_path: Path,
) -> None:
    runtime_dir = tmp_path / "runtimes"
    _ = _make_executable(runtime_dir / "bin" / "go")

    with _temporary_env(
        {
            "PLATFORM_RUNTIME_DIR": str(runtime_dir),
            "CODE_RUNNER_GO_BIN": str(tmp_path / "missing-go"),
            "PATH": "",
        }
    ):
        assert resolve_runtime_executable("go", override_env="CODE_RUNNER_GO_BIN") is None


def test_resolves_path_runtime_when_managed_runtime_is_absent(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtimes"
    path_bin = tmp_path / "path-bin"
    node_bin = _make_executable(path_bin / "node")

    with _temporary_env(
        {
            "PLATFORM_RUNTIME_DIR": str(runtime_dir),
            "CODE_RUNNER_NODE_BIN": None,
            "PATH": str(path_bin),
        }
    ):
        assert resolve_runtime_executable("node", override_env="CODE_RUNNER_NODE_BIN") == str(
            node_bin
        )


def test_missing_runtime_message_lists_canonical_sources(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtimes"

    with _temporary_env(
        {
            "PLATFORM_RUNTIME_DIR": str(runtime_dir),
            "CODE_RUNNER_GO_BIN": None,
            "PATH": "",
        }
    ):
        message = runtime_executable_required_message(
            "go",
            override_env="CODE_RUNNER_GO_BIN",
        )

    assert "go executable is required" in message
    assert "$PLATFORM_RUNTIME_DIR/bin/go" in message
    assert "PATH:go" in message
    assert "$CODE_RUNNER_GO_BIN" in message
