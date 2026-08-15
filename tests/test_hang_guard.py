"""Предикат hang-guard: idle не убиваем, зависший call/setup — да."""

from tests.hang_guard import WorkerHeartbeat, heartbeat_is_hung, hung_worker_deadline_seconds


def test_idle_worker_waiting_for_next_test_is_not_hung() -> None:
    heartbeat: WorkerHeartbeat = {
        "worker": "gw0",
        "pid": 4242,
        "nodeid": "tests/foo.py::test_a",
        "phase": "idle",
        "timeout_sec": 5.0,
        "monotonic": 100.0,
        "time": 1.0,
    }
    assert hung_worker_deadline_seconds(phase="idle", timeout_sec=5.0) == float("inf")
    assert heartbeat_is_hung(heartbeat, now_monotonic=100.0 + 600.0) is False


def test_call_past_timeout_plus_slack_is_hung() -> None:
    heartbeat: WorkerHeartbeat = {
        "worker": "gw3",
        "pid": 99,
        "nodeid": "tests/foo.py::test_a",
        "phase": "call",
        "timeout_sec": 5.0,
        "monotonic": 100.0,
        "time": 1.0,
    }
    assert heartbeat_is_hung(heartbeat, now_monotonic=100.0 + 5.0 + 14.0) is False
    assert heartbeat_is_hung(heartbeat, now_monotonic=100.0 + 5.0 + 15.1) is True


def test_setup_uses_floor_so_readiness_retry_is_not_killed() -> None:
    heartbeat: WorkerHeartbeat = {
        "worker": "gw1",
        "pid": 7,
        "nodeid": "tests/foo.py::test_a",
        "phase": "setup",
        "timeout_sec": 5.0,
        "monotonic": 100.0,
        "time": 1.0,
    }
    assert heartbeat_is_hung(heartbeat, now_monotonic=100.0 + 50.0) is False
    assert heartbeat_is_hung(heartbeat, now_monotonic=100.0 + 60.0 + 15.1) is True
