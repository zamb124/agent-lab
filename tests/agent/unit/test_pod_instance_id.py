"""Id пода tunnel bus: hostname процесса, подмена для второго пода в том же интерпретаторе."""

import os
import socket

import pytest

from apps.agent.tunnel_bus import bind_pod_instance_id, get_pod_instance_id


def test_get_pod_instance_id_uses_hostname_and_pid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOSTNAME", raising=False)
    hostname = socket.gethostname().strip()
    assert get_pod_instance_id() == f"{hostname}-{os.getpid()}"


def test_bind_pod_instance_id_overrides_and_restores(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HOSTNAME", raising=False)
    previous = bind_pod_instance_id("pod-b-test")
    try:
        assert get_pod_instance_id() == "pod-b-test"
    finally:
        restored = bind_pod_instance_id(previous)
        assert restored == "pod-b-test"
    assert get_pod_instance_id() == f"{socket.gethostname().strip()}-{os.getpid()}"
