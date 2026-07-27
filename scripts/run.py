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
    python scripts/run.py provider_litserve # Запуск provider_litserve (локальные эмбеддинги/реранк, через granian)
    python scripts/run.py flows_worker # Запуск TaskIQ flows_worker
    python scripts/run.py scheduler   # Запуск TaskIQ scheduler
    python scripts/run.py scheduler-api  # Запуск scheduler API
    python scripts/run.py browser       # Browser Runtime (Playwright + CDP)
    python scripts/run.py search        # Search MCP service
    python scripts/run.py capability_gateway # Trusted sandbox capabilities
    python scripts/run.py code_runner_python # Python sandbox runner
    python scripts/run.py code_runner_node   # JavaScript/TypeScript sandbox runner
    python scripts/run.py code_runner_go     # Go sandbox runner
    python scripts/run.py code_runner_csharp # C# sandbox runner
    python scripts/run.py rag_worker  # Запуск RAG worker
    python scripts/run.py sync_worker # Запуск Sync worker
    python scripts/run.py crm_worker  # Запуск CRM worker
    python scripts/run.py idle_worker # Запуск Idle worker
    python scripts/run.py all         # Все сервисы через mprocs (раздельные логи)
    python scripts/run.py all --kill  # то же, после SIGKILL процессов на портах HTTP-сервисов
    python scripts/run.py all -e flows_worker  # all без перечисленных сервисов (см. --exclude)
    python scripts/run.py from-make app --ex flows_worker  # вызывается из make app --ex ... (см. mk/app.mk)
    python scripts/run.py kill-ports  # только освободить порты HTTP-сервисов

Исключение из all: --exclude / -e / --ex, либо ex|x (следом имя), либо APP_EXCLUDE=… .
    make: «make app ex flows_worker»; с «--ex» на macOS см. «make -- app --ex …» в mk/app.mk.
    Требуется: brew install mprocs. Конфиг по умолчанию — mprocs.yaml.

Конфигурация загружается из conf.json и conf.local.json.
Переменные окружения имеют приоритет над конфигами.
"""
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Парные --static-path-route / --static-path-mount: реестр статики по сервисам
# (Granian отдаёт Rust-ом, не касаясь ASGI; FastAPI StaticFiles остаётся как
# fallback для in-process тестов через httpx.ASGITransport).
CORE_FRONTEND_STATIC = ("/static/core", "core/frontend/static")

# Конфигурация сервисов (HTTP — granian, taskiq — taskiq CLI, module — python -m)
SERVICES = {
    "flows": {
        "type": "granian",
        "app": "apps.flows.main:app",
        "port": "8001",
        "static": [
            CORE_FRONTEND_STATIC,
            ("/flows/static", "apps/flows/ui"),
            ("/static", "apps/flows/static"),
            ("/flows/demo_cards", "apps/flows/static/demo_cards"),
        ],
    },
    "frontend": {
        "type": "granian",
        "app": "apps.frontend.main:app",
        "port": "8002",
        "static": [
            CORE_FRONTEND_STATIC,
            ("/static/frontend", "apps/frontend/ui"),
        ],
    },
    "crm": {
        "type": "granian",
        "app": "apps.crm.main:app",
        "port": "8003",
        "static": [
            CORE_FRONTEND_STATIC,
            ("/crm/ui/static", "apps/crm/ui"),
            ("/crm/ui/vendor/3d-force-graph", "node_modules/3d-force-graph/dist"),
            ("/crm/ui/vendor/three", "node_modules/three/build"),
        ],
    },
    "rag": {
        "type": "granian",
        "app": "apps.rag.main:app",
        "port": "8004",
        "static": [
            CORE_FRONTEND_STATIC,
            ("/rag/ui/static", "apps/rag/ui"),
        ],
    },
    "sync": {
        "type": "granian",
        "app": "apps.sync.main:app",
        "port": "8005",
        "static": [
            CORE_FRONTEND_STATIC,
            ("/sync/ui/static", "apps/sync/ui"),
        ],
    },
    "office": {
        "type": "granian",
        "app": "apps.office.main:app",
        "port": "8008",
        "static": [
            CORE_FRONTEND_STATIC,
            ("/documents/ui/static", "apps/office/ui"),
        ],
    },
    "worktracker": {
        "type": "granian",
        "app": "apps.worktracker.main:app",
        "port": "8021",
        "static": [
            CORE_FRONTEND_STATIC,
            ("/worktracker/ui/static", "apps/worktracker/ui"),
        ],
    },
    "scheduler-api": {
        "type": "granian",
        "app": "apps.scheduler.main:app",
        "port": "8006",
    },
    "secrets": {
        "type": "granian",
        "app": "apps.secrets.main:app",
        "port": "8022",
    },
    "wiki": {
        "type": "granian",
        "app": "apps.wiki.main:app",
        "port": "8023",
        "static": [
            CORE_FRONTEND_STATIC,
            ("/wiki/ui/static", "apps/wiki/ui"),
        ],
    },
    "browser": {
        "type": "granian",
        "app": "apps.browser.main:app",
        "port": "8009",
        "env": {
            "BROWSER__CDP_URL": "http://127.0.0.1:9222",
        },
    },
    "search": {
        "type": "granian",
        "app": "apps.search.main:app",
        "port": "8010",
    },
    "provider_litserve": {
        "type": "granian",
        "app": "apps.provider_litserve.main:app",
        "port": "8014",
        "static": [
            CORE_FRONTEND_STATIC,
            ("/litserve/ui/static", "apps/provider_litserve/ui"),
        ],
    },

    "voice": {
        "type": "granian",
        "app": "apps.voice.main:app",
        "port": "8015",
    },
    "capability_gateway": {
        "type": "granian",
        "app": "apps.capability_gateway.main:app",
        "port": "8016",
    },
    "code_runner_python": {
        "type": "granian",
        "app": "apps.code_runner_python.main:app",
        "port": "8017",
    },
    "code_runner_node": {
        "type": "granian",
        "app": "apps.code_runner_node.main:app",
        "port": "8018",
    },
    "code_runner_go": {
        "type": "granian",
        "app": "apps.code_runner_go.main:app",
        "port": "8019",
    },
    "code_runner_csharp": {
        "type": "granian",
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
    "search_worker": {
        "type": "taskiq-worker",
        "worker_app": "apps.search_worker.worker:worker_app",
        "workers": "2",
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

# Granian --reload удобен для dev, но сервисы с multiprocessing + тяжёлым runtime
# (LitServe/torch, Playwright) на reload часто не освобождают память: старые worker'ы
# остаются с PPID=1 и копят RSS до OOM. В тестах и prod reload нет.
GRANIAN_RELOAD_DISABLED_SERVICES = frozenset({"provider_litserve", "browser"})

GRANIAN_RELOAD_IGNORE_DIRS = (
    "__pycache__",
    ".pytest_cache",
    ".git",
    ".venv",
    "node_modules",
    "reports",
    "data",
    ".cursor",
    "documentation-dist",
)


def _granian_reload_enabled(service: str) -> bool:
    raw = os.environ.get("APP_RELOAD", "1").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    return service not in GRANIAN_RELOAD_DISABLED_SERVICES


def _granian_reload_apps_path(service: str) -> str:
    """Каталог apps/<pkg> для watch: из module path SERVICES[service].app.

    Нельзя watch'ить весь apps/: правка flows UI иначе релоадит rag/crm/...
    и может оставить granian без живого worker (LISTEN без HTTP).
    """
    config = SERVICES[service]
    app_ref = config.get("app")
    if not isinstance(app_ref, str) or not app_ref:
        raise ValueError(f"SERVICES[{service!r}].app must be non-empty str for reload-paths")
    module_path = app_ref.split(":", 1)[0]
    parts = module_path.split(".")
    if len(parts) < 2 or parts[0] != "apps":
        raise ValueError(
            f"SERVICES[{service!r}].app must be apps.<pkg>...., got {app_ref!r}"
        )
    return f"apps/{parts[1]}"


def _append_granian_reload_args(cmd: list[str], *, service: str) -> None:
    if not _granian_reload_enabled(service):
        return
    cmd.append("--reload")
    # Per-service apps/<pkg> + shared core — не весь apps/.
    for path in (_granian_reload_apps_path(service), "core"):
        cmd += ["--reload-paths", path]
    for ignore_dir in GRANIAN_RELOAD_IGNORE_DIRS:
        cmd += ["--reload-ignore-dirs", ignore_dir]
    for ignore_path in ("reports", "data"):
        cmd += ["--reload-ignore-paths", ignore_path]


def _python_m_prefix() -> list[str]:
    uv_bin = shutil.which("uv")
    if uv_bin is not None:
        return [uv_bin, "run", "python", "-u", "-m"]
    return [sys.executable, "-u", "-m"]


def build_command(service: str) -> list[str]:
    if service not in SERVICES:
        raise ValueError(f"Неизвестный сервис: {service}")
    config = SERVICES[service]
    service_type = str(config["type"])
    if service_type == "granian":
        cmd: list[str] = _python_m_prefix() + [
            "granian",
            "--interface",
            "asgi",
            str(config["app"]),
            "--host",
            "0.0.0.0",
            "--port",
            str(config["port"]),
            "--http",
            "auto",
            "--ws",
            "--no-access-log",
        ]
        _append_granian_reload_args(cmd, service=service)
        static = config.get("static") or []
        if not isinstance(static, list):
            raise ValueError(f"SERVICES[{service!r}].static must be list[tuple[str,str]]")
        for route, mount in static:
            if not Path(mount).exists():
                continue
            cmd += ["--static-path-route", route, "--static-path-mount", mount]
        return cmd
    if service_type == "taskiq-worker":
        worker_app = config.get("worker_app")
        workers = config.get("workers")
        if not isinstance(worker_app, str):
            raise ValueError(f"SERVICES[{service!r}].worker_app must be str")
        if not isinstance(workers, str):
            raise ValueError(f"SERVICES[{service!r}].workers must be str")
        return _python_m_prefix() + [
            "taskiq",
            "worker",
            worker_app,
            "--workers",
            workers,
        ]
    if service_type == "taskiq-scheduler":
        scheduler = config.get("scheduler")
        if not isinstance(scheduler, str):
            raise ValueError(f"SERVICES[{service!r}].scheduler must be str")
        return _python_m_prefix() + [
            "taskiq",
            "scheduler",
            scheduler,
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


def _http_ports() -> list[str]:
    return [str(cfg["port"]) for cfg in SERVICES.values() if cfg["type"] == "granian"]


def kill_ports() -> None:
    """Завершает процессы, слушающие порты HTTP-сервисов (granian)."""
    ports = _http_ports()
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


def _require_mprocs() -> str:
    mprocs_bin = shutil.which("mprocs")
    if mprocs_bin is None:
        print(
            "mprocs не найден. Установи: brew install mprocs",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)
    return mprocs_bin


def _mprocs_proc_key(name: str) -> str:
    if "-" in name:
        return f'"{name}"'
    return name


def _render_mprocs_yaml(names: list[str]) -> str:
    lines = [
        "# Generated by scripts/run.py (APP_EXCLUDE / --ex).",
        "procs:",
    ]
    for name in names:
        lines.append(f"  {_mprocs_proc_key(name)}:")
        lines.append(f'    shell: "uv run python scripts/run.py {name}"')
    lines.append("")
    return "\n".join(lines)


def run_all(exclude: set[str] | None = None) -> None:
    """Запускает все сервисы через mprocs: один терминал, логи по выбранному процессу."""
    skip: set[str] = set(exclude) if exclude is not None else set()
    names = [n for n in SERVICES if n not in skip]
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

    mprocs_bin = _require_mprocs()
    if skip:
        fd, config_path_str = tempfile.mkstemp(
            prefix="agent-lab-mprocs-",
            suffix=".yaml",
        )
        os.close(fd)
        config_path = Path(config_path_str)
        _ = config_path.write_text(_render_mprocs_yaml(names), encoding="utf-8")
    else:
        config_path = project_root / "mprocs.yaml"
        if not config_path.is_file():
            print(
                f"Нет конфига mprocs: {config_path}",
                file=sys.stderr,
                flush=True,
            )
            sys.exit(1)

    print(
        (
            f"mprocs: {len(names)} процессов, конфиг {config_path}. "
            "j/k — сервис, Ctrl-a — фокус, r — restart, q — выход."
        ),
        flush=True,
    )
    os.chdir(project_root)
    os.execvp(mprocs_bin, [mprocs_bin, "-c", str(config_path)])


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
