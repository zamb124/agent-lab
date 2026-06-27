"""Тесты orchestrator scripts/agent_build.py."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from apps.agent.desktop.build_contract import (
    artifact_path as contract_artifact_path,
    load_default_distro_config,
)
from scripts import agent_build as agent_build_module


def test_publish_release_missing_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    version_sha = f"missing-{uuid.uuid4().hex[:12]}"
    monkeypatch.setattr(agent_build_module, "DIST_DIR", tmp_path)
    with pytest.raises(FileNotFoundError, match="Missing HumanitecAgent artifacts"):
        agent_build_module.publish_release(
            release_tag="humanitec-agent-v0.0.0-test",
            version_sha=version_sha,
        )


def test_ensure_local_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    version_sha = f"idempotent-{uuid.uuid4().hex[:12]}"
    monkeypatch.setattr(agent_build_module, "DIST_DIR", tmp_path)
    host_platform = agent_build_module.detect_host_platform()
    distro = load_default_distro_config()
    expected = contract_artifact_path(tmp_path, host_platform, version_sha, distro)
    expected.parent.mkdir(parents=True, exist_ok=True)
    expected.write_bytes(b"placeholder-artifact")

    build_calls: list[dict[str, str]] = []

    def _fake_build_platform(**kwargs: str) -> Path:
        build_calls.append(kwargs)
        return expected

    monkeypatch.setattr(agent_build_module, "build_platform", _fake_build_platform)

    first = agent_build_module.ensure_local(artifact_mode="placeholder", version_sha=version_sha)
    second = agent_build_module.ensure_local(artifact_mode="placeholder", version_sha=version_sha)

    assert first == expected
    assert second == expected
    assert build_calls == []
