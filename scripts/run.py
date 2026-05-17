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
    python scripts/run.py provider_litserve # Запуск provider_litserve (локальные эмбеддинги/реранк)
    python scripts/run.py flows_worker # Запуск TaskIQ flows_worker
    python scripts/run.py scheduler   # Запуск TaskIQ scheduler
    python scripts/run.py scheduler-api  # Запуск scheduler API
    python scripts/run.py browser       # Browser Runtime (Playwright + CDP)
    python scripts/run.py capability_gateway # Trusted sandbox capabilities
    python scripts/run.py code_runner_python # Python sandbox runner
    python scripts/run.py code_runner_node   # JavaScript/TypeScript sandbox runner
    python scripts/run.py code_runner_go     # Go sandbox runner
    python scripts/run.py code_runner_csharp # C# sandbox runner
    python scripts/run.py rag_worker  # Запуск RAG worker
    python scripts/run.py sync_worker # Запуск Sync worker
    python scripts/run.py crm_worker  # Запуск CRM worker
    python scripts/run.py idle_worker # Запуск Idle worker
    python scripts/run.py all         # Все сервисы параллельно (make app)
    python scripts/run.py all --kill  # то же, после SIGKILL процессов на портах HTTP-сервисов
    python scripts/run.py all -e flows_worker  # all без перечисленных сервисов (см. --exclude)
    python scripts/run.py from-make app --ex flows_worker  # вызывается из make app --ex ... (см. mk/app.mk)
    python scripts/run.py kill-ports  # только освободить порты HTTP-сервисов

Исключение из all: --exclude / -e / --ex, либо ex|x (следом имя), либо APP_EXCLUDE=… .
    make: «make app ex flows_worker»; с «--ex» на macOS см. «make -- app --ex …» в mk/app.mk.

Конфигурация загружается из conf.json и conf.local.json.
Переменные окружения имеют приоритет над конфигами.
"""
import os
import shutil
import signal
import subprocess
import sys
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
    "office": {
        "type": "uvicorn",
        "app": "apps.office.main:app",
        "port": "8008",
    },
    "scheduler-api": {
        "type": "uvicorn",
        "app": "apps.scheduler.main:app",
        "port": "8006",
    },
    "browser": {
        "type": "uvicorn",
        "app": "apps.browser.main:app",
        "port": "8009",
        "env": {
            "BROWSER__CDP_URL": "http://127.0.0.1:9222",
        },
    },
    "provider_litserve": {
        "type": "module",
        "module": "apps.provider_litserve.main",
        "port": "8014",
    },

    "voice": {
        "type": "uvicorn",
        "app": "apps.voice.main:app",
        "port": "8015",
    },
    "capability_gateway": {
        "type": "uvicorn",
        "app": "apps.capability_gateway.main:app",
        "port": "8016",
    },
    "code_runner_python": {
        "type": "uvicorn",
        "app": "apps.code_runner_python.main:app",
        "port": "8017",
    },
    "code_runner_node": {
        "type": "uvicorn",
        "app": "apps.code_runner_node.main:app",
        "port": "8018",
    },
    "code_runner_go": {
        "type": "uvicorn",
        "app": "apps.code_runner_go.main:app",
        "port": "8019",
    },
    "code_runner_csharp": {
        "type": "uvicorn",
        "app": "apps.code_runner_csharp.main:app",
        "port": "8020",
    },

    # TaskIQ workers
    "flows_worker": {
        "type": "taskiq-worker",
        "worker_app": "apps.flows_worker.worker:worker_app",
        "workers": "1",
    },
    "rag_worker": {
        "type": "taskiq-worker",
        "worker_app": "apps.rag_worker.worker:worker_app",
        "workers": "1",
    },
    "sync_worker": {
        "type": "taskiq-worker",
        "worker_app": "apps.sync_worker.worker:worker_app",
        "workers": "1",
    },
    "crm_worker": {
        "type": "taskiq-worker",
        "worker_app": "apps.crm_worker.worker:worker_app",
        "workers": "1",
    },
    "idle_worker": {
        "type": "taskiq-worker",
        "worker_app": "apps.idle_worker.worker:worker_app",
        "workers": "1",
    },

    # TaskIQ scheduler
    "scheduler": {
        "type": "taskiq-scheduler",
        "scheduler": "apps.scheduler.scheduler:scheduler",
    },
}


def _python_m_prefix() -> list[str]:
    uv_bin = shutil.which("uv")
    if uv_bin is not None:
        return [uv_bin, "run", "python", "-u", "-m"]
    return [sys.executable, "-u", "-m"]


def build_command(service: str) -> list[str]:
    if service not in SERVICES:
        raise ValueError(f"Неизвестный сервис: {service}")
    config = SERVICES[service]
    service_type = config["type"]
    if service_type == "uvicorn":
        return _python_m_prefix() + [
            "uvicorn",
            config["app"],
            "--host",
            "0.0.0.0",
            "--port",
            config["port"],
            "--reload",
            "--no-access-log",
        ]
    if service_type == "taskiq-worker":
        return _python_m_prefix() + [
            "taskiq",
            "worker",
            config["worker_app"],
            "--workers",
            config["workers"],
        ]
    if service_type == "module":
        return _python_m_prefix() + [config["module"]]
    if service_type == "taskiq-scheduler":
        return _python_m_prefix() + [
            "taskiq",
            "scheduler",
            config["scheduler"],
        ]
    raise ValueError(f"Неизвестный тип сервиса: {service_type}")


def build_env(service: str) -> dict[str, str]:
    cfg = SERVICES.get(service) or {}
    extra = cfg.get("env") or {}
    if not isinstance(extra, dict):
        raise ValueError(f"SERVICES[{service!r}].env must be dict[str,str]")
    out = dict(os.environ)
    for k, v in extra.items():
        if v is None:
            continue
        out[str(k)] = str(v)
    return out


def _uvicorn_ports() -> list[str]:
    return [
        cfg["port"]
        for cfg in SERVICES.values()
        if cfg["type"] in {"uvicorn", "module"}
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


def _parse_exclude_from_argv(argv: list[str]) -> set[str]:
    out: set[str] = set()
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--exclude", "-e", "--ex"):
            if i + 1 >= len(argv):
                print(
                    "Ошибка: после --exclude / -e / --ex нужно имя сервиса.",
                    file=sys.stderr,
                    flush=True,
                )
                sys.exit(1)
            out.add(argv[i + 1])
            i += 2
        elif a in ("ex", "x"):
            if i + 1 >= len(argv):
                print(
                    "Ошибка: после ex / x (короткий синтаксис для make) нужно имя сервиса.",
                    file=sys.stderr,
                    flush=True,
                )
                sys.exit(1)
            out.add(argv[i + 1])
            i += 2
        else:
            i += 1
    return out


def _exclude_from_env() -> set[str]:
    raw = os.environ.get("APP_EXCLUDE", "").strip()
    if not raw:
        return set()
    return {p.strip() for p in raw.split(",") if p.strip()}


def _validate_exclude(exclude: set[str]) -> None:
    for name in exclude:
        if name not in SERVICES:
            print(
                f"Неизвестный сервис для исключения: {name}. "
                f"Доступно: {', '.join(SERVICES.keys())}",
                file=sys.stderr,
                flush=True,
            )
            sys.exit(1)


def _run_from_make() -> None:
    goals = sys.argv[2:]
    if not goals or goals[0] != "app":
        print(
            "from-make: первый аргумент — app, как в «make app …» ($MAKECMDGOALS).",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)
    rest: list[str] = list(goals[1:])
    if rest and rest[-1] == "--from-make-kill":
        from_make_kill = True
        rest = rest[:-1]
    else:
        from_make_kill = False
    if "--kill" in rest:
        from_make_kill = True
        rest = [t for t in rest if t != "--kill"]
    if from_make_kill or os.environ.get("APP_KILL") == "1":
        kill_ports()
    exclude = _parse_exclude_from_argv(rest) | _exclude_from_env()
    _validate_exclude(exclude)
    run_all(exclude=exclude)


def run_all(exclude: set[str] | None = None) -> None:
    skip = set(exclude) if exclude else set()
    names = [n for n in SERVICES.keys() if n not in skip]
    if not names:
        print(
            "Ошибка: после исключения не осталось сервисов для запуска.",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)
    if skip:
        print(
            f"Пропуск сервисов: {', '.join(sorted(skip))}",
            flush=True,
        )
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
            cwd=str(project_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=build_env(name),
        )
        assert proc.stdout is not None
        prefix = f"[{name}] "
        threading.Thread(
            target=_prefix_stream,
            args=(proc.stdout, prefix),
            name=f"run-all:{name}:stdout",
            daemon=True,
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
        print(
            f"Доступные сервисы: {', '.join(SERVICES.keys())}, all, from-make, kill-ports"
        )
        sys.exit(1)

    service = sys.argv[1]

    if service == "kill-ports":
        kill_ports()
        return

    if service == "from-make":
        _run_from_make()
        return

    if service == "all":
        rest = sys.argv[2:]
        if "--kill" in rest or os.environ.get("APP_KILL") == "1":
            kill_ports()
        exclude = _parse_exclude_from_argv(rest) | _exclude_from_env()
        _validate_exclude(exclude)
        run_all(exclude=exclude)
        return

    if service not in SERVICES:
        print(f"Неизвестный сервис: {service}")
        print(f"Доступные: {', '.join(SERVICES.keys())}, all, from-make, kill-ports")
        sys.exit(1)

    cmd = build_command(service)
    print(f"Запуск {service}: {' '.join(cmd)}", flush=True)
    result = subprocess.run(
        cmd,
        cwd=str(project_root),
        stdout=sys.stdout,
        stderr=sys.stderr,
        env=build_env(service),
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
