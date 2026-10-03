"""Мост language server получает сессию аргументами процесса."""

import json

import pytest

from core.capabilities.lsp_bridge import bridge_invocation


def test_bridge_invocation_reads_session_root_and_command() -> None:
    session_id, root, command = bridge_invocation(
        [
            "lsp_bridge.py",
            "session-1",
            "/tmp/platform-code-lsp-session-1",
            json.dumps(["gopls", "serve"]),
        ]
    )
    assert session_id == "session-1"
    assert root.as_posix() == "/tmp/platform-code-lsp-session-1"
    assert command == ["gopls", "serve"]


def test_bridge_invocation_rejects_short_argv() -> None:
    with pytest.raises(RuntimeError, match="session_id, root and command json"):
        _ = bridge_invocation(["lsp_bridge.py", "session-1"])


def test_bridge_invocation_rejects_empty_command() -> None:
    with pytest.raises(RuntimeError, match="must not be empty"):
        _ = bridge_invocation(
            ["lsp_bridge.py", "session-1", "/tmp/lsp", json.dumps([])],
        )
