#!/usr/bin/env python3
"""
Универсальный скрипт запуска сервисов для локальной разработки.

Использование:
    python scripts/run.py flows       # Запуск flows сервиса
    python scripts/run.py frontend    # Запуск frontend сервиса
    python scripts/run.py crm         # Запуск crm сервиса
    python scripts/run.py rag         # Запуск rag сервиса
    python scripts/run.py sync        # Запуск sync сервиса
    python scripts/run.py office      # Запуск office (Documents / OnlyOffice BFF + UI)
    python scripts/run.py flows_worker # Запуск TaskIQ flows_worker
    python scripts/run.py scheduler   # Запуск TaskIQ scheduler
    python scripts/run.py scheduler-api  # Запуск scheduler API
    python scripts/run.py rag_worker  # Запуск RAG worker
    python scripts/run.py sync_worker # Запуск Sync worker
    python scripts/run.py crm_worker  # Запуск CRM worker
    python scripts/run.py idle_worker # Запуск Idle worker
    python scripts/run.py all         # Все сервисы параллельно (make app)
    python scripts/run.py all --kill  # то же, после SIGKILL процессов на портах HTTP-сервисов
    python scripts/run.py kill-ports  # только освободить порты HTTP-сервисов

Конфигурация загружается из conf.json и conf.local.json.
Переменные окружения имеют приоритет над конфигами.
"""
import os
import signal
import sys
import subprocess
import threading
import time
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Конфигурация сервисов
SERVICES = {
    # FastAPI сервисы (uvicorn)
    "flows": {
        "type": "uvicorn",
        "app": "apps.app_runtime_targets:flows_app",
        "port": "8001",
    },
    "frontend": {
        "type": "uvicorn",
        "app": "apps.app_runtime_targets:frontend_app",
        "port": "8002",
    },
    "crm": {
        "type": "uvicorn",
        "app": "apps.app_runtime_targets:crm_app",
        "port": "8003",
    },
    "rag": {
        "type": "uvicorn",
        "app": "apps.app_runtime_targets:rag_app",
        "port": "8004",
    },
    "sync": {
        "type": "uvicorn",
        "app": "apps.app_runtime_targets:sync_app",
        "port": "8005",
    },
    "office": {
        "type": "uvicorn",
        "app": "apps.app_runtime_targets:office_app",
        "port": "8008",
    },
    "scheduler-api": {
        "type": "uvicorn",
        "app": "apps.app_runtime_targets:scheduler_app",
        "port": "8006",
    },
    
    # TaskIQ workers
    "flows_worker": {
        "type": "taskiq-worker",
        "worker_app": "apps.app_runtime_targets:flows_taskiq_worker_app",
        "workers": "1",
    },
    "rag_worker": {
        "type": "taskiq-worker",
        "worker_app": "apps.app_runtime_targets:rag_taskiq_worker_app",
        "workers": "1",
    },
    "sync_worker": {
        "type": "taskiq-worker",
        "worker_app": "apps.app_runtime_targets:sync_taskiq_worker_app",
        "workers": "1",
    },
    "crm_worker": {
        "type": "taskiq-worker",
        "worker_app": "apps.app_runtime_targets:crm_taskiq_worker_app",
        "workers": "1",
    },
    "idle_worker": {
        "type": "taskiq-worker",
        "worker_app": "apps.app_runtime_targets:idle_taskiq_worker_app",
        "workers": "1",
    },
    
    # TaskIQ scheduler
    "scheduler": {
        "type": "taskiq-scheduler",
        "scheduler": "apps.app_runtime_targets:platform_scheduler",
    },
}


def build_command(service: str) -> list[str]:
    if service not in SERVICES:
        raise ValueError(f"Неизвестный сервис: {service}")
    config = SERVICES[service]
    service_type = config["type"]
    if service_type == "uvicorn":
        return [
            sys.executable,
            "-u",
            "-m",
            "uvicorn",
            config["app"],
            "--host",
            "0.0.0.0",
            "--port",
            config["port"],
            "--reload",
            "--access-log",
        ]
    if service_type == "taskiq-worker":
        cmd = [
            sys.executable,
            "-u",
            "-m",
            "taskiq",
            "worker",
            config["worker_app"],
            "--workers",
            config["workers"],
        ]
        return cmd
    if service_type == "taskiq-scheduler":
        return [
            sys.executable,
            "-u",
            "-m",
            "taskiq",
            "scheduler",
            config["scheduler"],
        ]
    raise ValueError(f"Неизвестный тип сервиса: {service_type}")


def _uvicorn_ports() -> list[str]:
    return [
        cfg["port"]
        for cfg in SERVICES.values()
        if cfg["type"] == "uvicorn"
    ]


def kill_ports() -> None:
    """Завершает процессы, слушающие порты HTTP-сервисов (uvicorn)."""
    ports = _uvicorn_ports()
    killed: list[tuple[str, int]] = []
    for port in ports:
        listed = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if listed.returncode != 0 or not listed.stdout.strip():
            continue
        for pid_str in listed.stdout.strip().split():
            pid = int(pid_str)
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                continue
            killed.append((port, pid))
    if killed:
        for port, pid in killed:
            print(f"Освобождён порт {port}: завершён PID {pid}", flush=True)


def _prefix_stream(stream, prefix: str) -> None:
    for line in iter(stream.readline, ""):
        sys.stdout.write(f"{prefix}{line}")
        sys.stdout.flush()
    stream.close()


def run_all() -> None:
    names = list(SERVICES.keys())
    children: list[tuple[str, subprocess.Popen[str]]] = []

    def terminate_children() -> None:
        for name, proc in children:
            if proc.poll() is None:
                proc.terminate()
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            alive = [p for _, p in children if p.poll() is None]
            if not alive:
                return
            time.sleep(0.1)
        for _, proc in children:
            if proc.poll() is None:
                proc.kill()

    def handle_signal(_signum: int, _frame: object) -> None:
        terminate_children()
        sys.exit(130)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    for name in names:
        cmd = build_command(name)
        print(f"Запуск {name}: {' '.join(cmd)}", flush=True)
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        prefix = f"[{name}] "
        threading.Thread(
            target=_prefix_stream, args=(proc.stdout, prefix), daemon=True
        ).start()
        children.append((name, proc))

    reported_exits: set[str] = set()
    final_exit_code = 0
    try:
        while True:
            for name, proc in children:
                code = proc.poll()
                if code is not None and name not in reported_exits:
                    reported_exits.add(name)
                    print(
                        f"Процесс {name} завершился с кодом {code}. "
                        f"Остальные сервисы продолжают работу.",
                        flush=True,
                    )
                    if code != 0:
                        final_exit_code = code
            alive = [p for _, p in children if p.poll() is None]
            if not alive:
                sys.exit(final_exit_code)
            time.sleep(0.25)
    except KeyboardInterrupt:
        terminate_children()
        sys.exit(130)


def main() -> None:
    if len(sys.argv) < 2:
        print("Использование: python scripts/run.py <service>")
        print(f"Доступные сервисы: {', '.join(SERVICES.keys())}, all, kill-ports")
        sys.exit(1)

    service = sys.argv[1]

    if service == "kill-ports":
        kill_ports()
        return

    if service == "all":
        rest = sys.argv[2:]
        if "--kill" in rest or os.environ.get("APP_KILL") == "1":
            kill_ports()
        run_all()
        return

    if service not in SERVICES:
        print(f"Неизвестный сервис: {service}")
        print(f"Доступные: {', '.join(SERVICES.keys())}, all, kill-ports")
        sys.exit(1)

    cmd = build_command(service)
    print(f"Запуск {service}: {' '.join(cmd)}")
    result = subprocess.run(cmd, stdout=sys.stdout, stderr=sys.stderr)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
