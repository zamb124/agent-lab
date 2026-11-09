"""Preflight cleanup for local pytest runs.

Kills stale local processes created by pytest fixtures and test_stack before a
new test run. The matcher is intentionally narrow: HTTP ports and app modules
of the test stack (derived from ``scripts.testing.stack`` catalogs), pytest/
xdist from this repository, repo-cwd multiprocessing children, and Python
sandbox workers from ``/tmp/code-runner-python-runtime-*``.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import psutil

from scripts.testing.stack import build_granian_services, build_taskiq_worker_services

REPO_ROOT = Path(__file__).resolve().parents[2]
MARKER_DIR = Path("/tmp")
TEMP_DIR = Path(tempfile.gettempdir()).resolve()

# Каталоги — из test_stack, единый источник правды: новый сервис/порт стека
# попадает в матчер автоматически, без правки этого файла.
_GRANIAN_SERVICES = build_granian_services()
TEST_HTTP_PORTS = {service.port for service in _GRANIAN_SERVICES}
TEST_GRANIAN_APPS = tuple(service.app_path for service in _GRANIAN_SERVICES)
TEST_TASKIQ_APPS = tuple(
    worker.worker_module for worker in build_taskiq_worker_services()
) + (
    # conftest поднимает scheduler сабпроцессом вне стека (tests/fixtures/workers.py).
    "apps.scheduler.scheduler:scheduler",
)

TEST_MARKER_GLOBS = (
    "platform_test_*.pid",
    "platform_test_*.pid.refs",
    "platform_test_*.pid.ref_count",
    "platform_test_*.pid.envsig",
    "platform_test_*.pid.starting",
    "platform_test_*.done",
    "platform_test_*.lock",
)


@dataclass(frozen=True)
class Candidate:
    pid: int
    reason: str
    command: str


def _command(process: psutil.Process) -> str:
    try:
        cmdline = process.cmdline()
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
        return ""
    return " ".join(cmdline)


def _cwd_is_repo(process: psutil.Process) -> bool:
    try:
        cwd = Path(process.cwd()).resolve()
    except (OSError, psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
        return False
    try:
        return cwd == REPO_ROOT or REPO_ROOT in cwd.parents
    except RuntimeError:
        return False


def _protected_pids() -> set[int]:
    protected = {os.getpid(), os.getppid()}
    try:
        protected.update(parent.pid for parent in psutil.Process().parents())
    except (psutil.Error, OSError):
        pass
    return protected


def _listening_test_ports_by_pid() -> dict[int, set[int]]:
    by_pid: dict[int, set[int]] = {}
    for process in psutil.process_iter(["pid"]):
        try:
            connections = process.net_connections(kind="inet")
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
            continue
        for conn in connections:
            if conn.status != psutil.CONN_LISTEN:
                continue
            if conn.laddr and conn.laddr.port in TEST_HTTP_PORTS:
                by_pid.setdefault(process.pid, set()).add(conn.laddr.port)
    return by_pid


def _runtime_dir_from_command(command: str) -> Path | None:
    for token in command.split():
        if "/code-runner-python-runtime-" not in token:
            continue
        path = Path(token)
        if path.name == "python_worker.py":
            return path.parent
    return None


# Порт-форварды docker compose (Centrifugo :19000, Postgres, Redis, SeaweedFS) держит Docker Desktop:
# его процессы — не stale-тест, их убийство валит весь compose-стек.
_DOCKER_COMMAND_MARKERS: tuple[str, ...] = ("Docker.app", "com.docker.", "docker-proxy")


def _candidate_reason(process: psutil.Process, ports_by_pid: dict[int, set[int]]) -> str | None:
    command = _command(process)
    if not command:
        return None
    if any(marker in command for marker in _DOCKER_COMMAND_MARKERS):
        return None

    ports = ports_by_pid.get(process.pid)
    if ports:
        return "test-http-port:" + ",".join(str(port) for port in sorted(ports))

    if "code-runner-python-runtime-" in command and "python_worker.py" in command:
        return "code-runner-python-runtime"

    # Осиротевшие multiprocessing-дети (litserve spawn-воркеры, resource_tracker):
    # cmdline без pytest/портов — узнаём только по cwd внутри репозитория.
    if "multiprocessing" in command and _cwd_is_repo(process):
        return "repo-multiprocessing-child"

    if "granian" in command:
        for app_path in TEST_GRANIAN_APPS:
            if app_path in command:
                return f"test-granian:{app_path}"

    if "taskiq" in command:
        for app_path in TEST_TASKIQ_APPS:
            if app_path in command:
                return f"test-taskiq:{app_path}"

    if _cwd_is_repo(process) and "pytest" in command and "tests" in command:
        return "repo-pytest"

    return None


def _collect_candidates() -> dict[int, Candidate]:
    ports_by_pid = _listening_test_ports_by_pid()
    protected = _protected_pids()
    candidates: dict[int, Candidate] = {}

    for process in psutil.process_iter(["pid"]):
        pid = process.pid
        if pid in protected:
            continue
        reason = _candidate_reason(process, ports_by_pid)
        if reason is None:
            continue
        candidates[pid] = Candidate(pid=pid, reason=reason, command=_command(process))

    for pid in list(candidates):
        try:
            children = psutil.Process(pid).children(recursive=True)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        for child in children:
            if child.pid in protected or child.pid in candidates:
                continue
            candidates[child.pid] = Candidate(
                pid=child.pid,
                reason=f"child-of:{pid}",
                command=_command(child),
            )

    return dict(sorted(candidates.items()))


def _terminate(candidates: dict[int, Candidate], *, grace_seconds: float) -> tuple[int, int]:
    processes: list[psutil.Process] = []
    for pid in candidates:
        try:
            processes.append(psutil.Process(pid))
        except psutil.NoSuchProcess:
            continue

    for process in processes:
        try:
            process.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    gone, alive = psutil.wait_procs(processes, timeout=grace_seconds)
    for process in alive:
        try:
            process.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    killed_alive, still_alive = psutil.wait_procs(alive, timeout=2.0)
    return len(gone) + len(killed_alive), len(still_alive)


def _cleanup_markers() -> int:
    removed = 0
    for pattern in TEST_MARKER_GLOBS:
        for path in MARKER_DIR.glob(pattern):
            try:
                path.unlink()
            except FileNotFoundError:
                continue
            removed += 1
    return removed


def _cleanup_runtime_dirs(candidates: dict[int, Candidate]) -> int:
    runtime_dirs = {
        runtime_dir
        for candidate in candidates.values()
        if (runtime_dir := _runtime_dir_from_command(candidate.command)) is not None
    }
    removed = 0
    for runtime_dir in runtime_dirs:
        if not runtime_dir.exists():
            continue
        resolved_runtime_dir = runtime_dir.resolve()
        if resolved_runtime_dir.parent != TEMP_DIR or not resolved_runtime_dir.name.startswith(
            "code-runner-python-runtime-"
        ):
            raise RuntimeError(f"refusing to remove unexpected runtime dir: {runtime_dir}")
        shutil.rmtree(resolved_runtime_dir)
        removed += 1
    return removed


def _ports_still_listening() -> dict[int, set[int]]:
    by_pid = _listening_test_ports_by_pid()
    busy: dict[int, set[int]] = {}
    for pid, ports in by_pid.items():
        if pid in _protected_pids():
            continue
        busy[pid] = ports
    return busy


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--grace-seconds", type=float, default=3.0)
    args = parser.parse_args()

    candidates = _collect_candidates()
    if not candidates:
        marker_count = 0 if args.dry_run else _cleanup_markers()
        print(f"test_process_preflight_cleanup: процессов нет, markers_removed={marker_count}")
        return 0

    print(f"test_process_preflight_cleanup: найдено процессов={len(candidates)}")
    for candidate in candidates.values():
        short_command = candidate.command[:220]
        print(f"  pid={candidate.pid} reason={candidate.reason} cmd={short_command!r}")

    if args.dry_run:
        return 0

    killed, alive = _terminate(candidates, grace_seconds=args.grace_seconds)
    time.sleep(0.25)
    runtime_dirs_removed = _cleanup_runtime_dirs(candidates)
    markers_removed = _cleanup_markers()
    busy_ports = _ports_still_listening()
    print(
        "test_process_preflight_cleanup: "
        f"killed={killed}, alive={alive}, "
        f"runtime_dirs_removed={runtime_dirs_removed}, markers_removed={markers_removed}"
    )
    if busy_ports:
        print("test_process_preflight_cleanup: тестовые HTTP-порты всё ещё заняты:", file=sys.stderr)
        for pid, ports in sorted(busy_ports.items()):
            try:
                command = _command(psutil.Process(pid))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                command = ""
            short_command = command[:220]
            port_list = ",".join(str(port) for port in sorted(ports))
            print(
                f"  pid={pid} ports={port_list} cmd={short_command!r}",
                file=sys.stderr,
            )
        return 1
    if alive:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
