"""Предикат hang-guard: idle под нагрузкой не убиваем, зависший call/setup и
shutdown-тейл — да."""

from tests.hang_guard import (
    WorkerHeartbeat,
    heartbeat_is_hung,
    hung_worker_deadline_seconds,
)


def _heartbeat(phase: str, timeout_sec: float = 5.0) -> WorkerHeartbeat:
    return {
        "worker": "gw0",
        "pid": 4242,
        "nodeid": "tests/foo.py::test_a",
        "phase": phase,
        "timeout_sec": timeout_sec,
        "monotonic": 100.0,
        "time": 1.0,
    }


def test_idle_worker_waiting_for_next_test_is_not_hung() -> None:
    heartbeat = _heartbeat("idle")
    assert hung_worker_deadline_seconds(
        phase="idle", timeout_sec=5.0, global_active=True
    ) == float("inf")
    assert (
        heartbeat_is_hung(heartbeat, now_monotonic=100.0 + 600.0, global_active=True)
        is False
    )


def test_idle_worker_after_last_report_is_killed_on_grace() -> None:
    """Прогон кончился (никто не в setup/call/teardown): idle-процесс обязан
    выйти за grace — зависший teardown playwright-драйвера больше не маскируется."""
    heartbeat = _heartbeat("idle")
    assert (
        heartbeat_is_hung(heartbeat, now_monotonic=100.0 + 119.0, global_active=False)
        is False
    )
    assert (
        heartbeat_is_hung(heartbeat, now_monotonic=100.0 + 121.0, global_active=False)
        is True
    )


def test_session_finish_shutdown_tail_is_killed_on_grace() -> None:
    heartbeat = _heartbeat("session_finish", timeout_sec=0.0)
    assert (
        heartbeat_is_hung(heartbeat, now_monotonic=100.0 + 121.0, global_active=False)
        is True
    )
    assert (
        heartbeat_is_hung(heartbeat, now_monotonic=100.0 + 121.0, global_active=True)
        is False
    )


def test_session_start_is_never_hung() -> None:
    heartbeat = _heartbeat("session_start", timeout_sec=0.0)
    assert (
        heartbeat_is_hung(
            heartbeat, now_monotonic=100.0 + 9999.0, global_active=False
        )
        is False
    )


def test_call_past_timeout_plus_slack_is_hung() -> None:
    heartbeat = _heartbeat("call")
    assert (
        heartbeat_is_hung(
            heartbeat, now_monotonic=100.0 + 5.0 + 14.0, global_active=True
        )
        is False
    )
    assert (
        heartbeat_is_hung(
            heartbeat, now_monotonic=100.0 + 5.0 + 15.1, global_active=True
        )
        is True
    )


def test_setup_uses_floor_so_readiness_retry_is_not_killed() -> None:
    heartbeat = _heartbeat("setup")
    assert (
        heartbeat_is_hung(heartbeat, now_monotonic=100.0 + 50.0, global_active=True)
        is False
    )
    assert (
        heartbeat_is_hung(
            heartbeat, now_monotonic=100.0 + 60.0 + 15.1, global_active=True
        )
        is True
    )
