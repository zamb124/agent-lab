"""inprocess наследует PATH, HOME и LANG процесса фермы."""

import pytest

from core.guest_runtime.env import apply_inprocess_host_env, guest_host_path


def test_guest_host_path_rejects_blank() -> None:
    with pytest.raises(RuntimeError, match="PATH is required"):
        _ = guest_host_path({"PATH": "  "})


def test_apply_inprocess_host_env_copies_nonempty_home_and_lang() -> None:
    env: dict[str, str] = {}
    apply_inprocess_host_env(
        env,
        {"PATH": "/usr/bin", "HOME": "/Users/dev", "LANG": "  "},
    )
    assert env["PATH"] == "/usr/bin"
    assert env["HOME"] == "/Users/dev"
    assert "LANG" not in env
