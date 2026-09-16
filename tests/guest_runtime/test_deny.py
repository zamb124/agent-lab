from __future__ import annotations

import pytest

from apps.guest_runtime.services.deny import assert_source_allowed
from core.guest_runtime.models import CodeAgentSourceFile


def test_assert_source_allowed_rejects_torch_requirement() -> None:
    files = [
        CodeAgentSourceFile(file_id="f1", relative_path="requirements.txt", file_size=12),
    ]
    with pytest.raises(ValueError, match="torch"):
        assert_source_allowed(files, {"requirements.txt": b"torch==2.0\n"})


def test_assert_source_allowed_rejects_cuda_requirement() -> None:
    files = [
        CodeAgentSourceFile(file_id="f4", relative_path="requirements.txt", file_size=9),
    ]
    with pytest.raises(ValueError, match="cuda"):
        assert_source_allowed(files, {"requirements.txt": b"cuda-python\n"})


def test_assert_source_allowed_accepts_lockfile() -> None:
    files = [
        CodeAgentSourceFile(file_id="f2", relative_path="uv.lock", file_size=24),
    ]
    assert_source_allowed(files, {"uv.lock": b'version = 1\nrevision = 1\n'})


def test_assert_source_allowed_rejects_torch_in_lockfile() -> None:
    files = [
        CodeAgentSourceFile(file_id="f5", relative_path="uv.lock", file_size=20),
    ]
    with pytest.raises(ValueError, match="torch"):
        assert_source_allowed(files, {"uv.lock": b'name = "torch"\n'})


def test_assert_source_allowed_accepts_plain_python() -> None:
    files = [
        CodeAgentSourceFile(file_id="f3", relative_path="main.py", file_size=15),
    ]
    assert_source_allowed(files, {"main.py": b'print("ok")\n'})
