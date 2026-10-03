"""child_process_env копирует окружение родителя и не мутирует его."""

import os

import pytest

from core.utils.process_env import child_process_env


def test_child_process_env_overrides_without_mutating_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHILD_PROCESS_ENV_PROBE", "parent")
    env = child_process_env(
        {
            "CHILD_PROCESS_ENV_PROBE": "child",
            "CHILD_PROCESS_ENV_ADDED": "1",
        }
    )
    env["CHILD_PROCESS_ENV_PROBE"] = "mutated"
    assert env["CHILD_PROCESS_ENV_PROBE"] == "mutated"
    assert env["CHILD_PROCESS_ENV_ADDED"] == "1"
    assert os.environ["CHILD_PROCESS_ENV_PROBE"] == "parent"
