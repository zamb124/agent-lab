"""Сигнал процессу гостя: отсутствующий pid — не ошибка оркестрации."""

import os
import subprocess
import sys

from apps.guest_runtime.services.slots import signal_process


def test_signal_process_alive_pid_signal_zero() -> None:
    assert signal_process(os.getpid(), 0) is True


def test_signal_process_exited_pid_is_absent() -> None:
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    _ = proc.wait()
    assert signal_process(proc.pid, 0) is False
