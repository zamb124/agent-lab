#!/usr/bin/env python3
"""
Универсальный скрипт запуска сервисов для локальной разработки.

Использование:
    python scripts/run.py flows       # Запуск flows сервиса
    python scripts/run.py frontend    # Запуск frontend сервиса
    python scripts/run.py crm         # Запуск crm сервиса
    python scripts/run.py rag         # Запуск rag сервиса
    python scripts/run.py sync        # Запуск sync сервиса
    python scripts/run.py worker      # Запуск TaskIQ worker
    python scripts/run.py scheduler   # Запуск TaskIQ scheduler
    python scripts/run.py rag-worker  # Запуск RAG worker
    python scripts/run.py sync-worker # Запуск Sync worker
    python scripts/run.py all         # Все сервисы параллельно (make app)

Конфигурация загружается из conf.json и conf.local.json.
Переменные окружения имеют приоритет над конфигами.
"""
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
        "app": "apps.flows.main:app",
        "port": "8001",
    },
    "frontend": {
        "type": "uvicorn",
        "app": "apps.frontend.main:app",
        "port": "8002",
    },
    "crm": {
        "type": "uvicorn",
        "app": "apps.crm.main:app",
        "port": "8003",
    },
    "rag": {
        "type": "uvicorn",
        "app": "apps.rag.main:app",
        "port": "8004",
    },
    "sync": {
        "type": "uvicorn",
        "app": "apps.sync.main:app",
        "port": "8005",
    },
    
    # TaskIQ workers
    "worker": {
        "type": "taskiq-worker",
        "broker": "apps.broker.worker:broker",
        "workers": "1",
    },
    "rag-worker": {
        "type": "taskiq-worker",
        "broker": "apps.rag_worker.worker:broker",
        "workers": "1",
    },
    "sync-worker": {
        "type": "taskiq-worker",
        "broker": "apps.sync_worker.worker:broker",
        "workers": "1",
    },
    
    # TaskIQ scheduler
    "scheduler": {
        "type": "taskiq-scheduler",
        "scheduler": "apps.scheduler.scheduler:scheduler",
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
            config["broker"],
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
        print(f"Доступные сервисы: {', '.join(SERVICES.keys())}, all")
        sys.exit(1)

    service = sys.argv[1]

    if service == "all":
        run_all()
        return

    if service not in SERVICES:
        print(f"Неизвестный сервис: {service}")
        print(f"Доступные: {', '.join(SERVICES.keys())}, all")
        sys.exit(1)

    cmd = build_command(service)
    print(f"Запуск {service}: {' '.join(cmd)}")
    result = subprocess.run(cmd, stdout=sys.stdout, stderr=sys.stderr)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
