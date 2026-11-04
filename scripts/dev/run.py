#!/usr/bin/env python3
"""
Универсальный скрипт запуска сервисов для локальной разработки.

Использование:
    python -m scripts.dev.run flows       # Запуск flows сервиса
    python -m scripts.dev.run frontend    # Запуск frontend сервиса
    python -m scripts.dev.run crm         # Запуск crm сервиса
    python -m scripts.dev.run rag         # Запуск rag сервиса
    python -m scripts.dev.run sync        # Запуск sync сервиса
    python -m scripts.dev.run office      # Запуск office (Documents / OnlyOffice BFF + UI)
    python -m scripts.dev.run provider_litserve # Запуск provider_litserve (локальные эмбеддинги/реранк, через granian)
    python -m scripts.dev.run flows_worker # Запуск TaskIQ flows_worker
    python -m scripts.dev.run scheduler   # Запуск TaskIQ scheduler
    python -m scripts.dev.run scheduler-api  # Запуск scheduler API
    python -m scripts.dev.run browser       # Browser Runtime (Playwright + CDP)
    python -m scripts.dev.run search        # Search MCP service
    python -m scripts.dev.run capability_gateway # Trusted sandbox capabilities
    python -m scripts.dev.run code_runner_python # Python sandbox runner
    python -m scripts.dev.run code_runner_node   # JavaScript/TypeScript sandbox runner
    python -m scripts.dev.run code_runner_go     # Go sandbox runner
    python -m scripts.dev.run code_runner_csharp # C# sandbox runner
    python -m scripts.dev.run rag_worker  # Запуск RAG worker
    python -m scripts.dev.run sync_worker # Запуск Sync worker
    python -m scripts.dev.run crm_worker  # Запуск CRM worker
    python -m scripts.dev.run crm_summary_worker  # Запуск CRM daily/period summary worker
    python -m scripts.dev.run idle_worker # Запуск Idle worker
    python -m scripts.dev.run all         # Все сервисы через mprocs (раздельные логи)
    python -m scripts.dev.run all --kill  # устаревший флаг: сироты стека зачищаются всегда
    python -m scripts.dev.run all -e flows_worker  # all без перечисленных сервисов (см. --exclude)
    python -m scripts.dev.run from-make app --ex flows_worker  # вызывается из make app --ex ... (см. mk/app.mk)
    python -m scripts.dev.run kill-ports  # зачистка сирот: порты HTTP-сервисов + процессы прошлых запусков

Исключение из all: --exclude / -e / --ex, либо ex|x (следом имя), либо APP_EXCLUDE=… .
    make: «make app ex flows_worker»; с «--ex» на macOS см. «make -- app --ex …» в mk/app.mk.
    Требуется: brew install mprocs. Конфиг по умолчанию — mprocs.yaml.

Конфигурация загружается из conf.json и conf.local.json.
Переменные окружения имеют приоритет над конфигами.
Перед стартом сервисов подгружается reports/openfga-dev.env (после make dev-up).
"""
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
project_root = Path(__file__).parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Парные --static-path-route / --static-path-mount: реестр статики по сервисам
# (Granian отдаёт Rust-ом, не касаясь ASGI; FastAPI StaticFiles остаётся как
# fallback для in-process тестов через httpx2.ASGITransport).
CORE_FRONTEND_STATIC = ("/static/core", "core/frontend/static")
# granian берёт первый совпавший маршрут: embed-бандлы `/static/core/lib/*` объявляются до `/static/core`.
CORE_FRONTEND_EMBED = ("/static/core/lib", "core/frontend/embed-dist")

# Конфигурация сервисов (HTTP — granian, taskiq — taskiq CLI, module — python -m)
SERVICES = {
    "ui_watch": {
        "type": "npm-script",
        "script": "watch:ui",
    },
    "flows": {
        "type": "granian",
        "app": "apps.flows.main:app",
        "port": "8001",
        "static": [
            CORE_FRONTEND_EMBED,
            CORE_FRONTEND_STATIC,
            ("/flows/static", "apps/flows/ui-dist"),
            ("/static", "apps/flows/static"),
            ("/flows/demo_cards", "apps/flows/static/demo_cards"),
        ],
    },
    "frontend": {
        "type": "granian",
        "app": "apps.frontend.main:app",
        "port": "8002",
        "static": [
            CORE_FRONTEND_EMBED,
            CORE_FRONTEND_STATIC,
            ("/static/frontend", "apps/frontend/ui-dist"),
        ],
    },
    "crm": {
        "type": "granian",
        "app": "apps.crm.main:app",
        "port": "8003",
        "static": [
            CORE_FRONTEND_EMBED,
            CORE_FRONTEND_STATIC,
            ("/crm/ui/static", "apps/crm/ui-dist"),
        ],
    },
    "rag": {
        "type": "granian",
        "app": "apps.rag.main:app",
        "port": "8004",
        "static": [
            CORE_FRONTEND_EMBED,
            CORE_FRONTEND_STATIC,
            ("/rag/ui/static", "apps/rag/ui-dist"),
        ],
    },
    "sync": {
        "type": "granian",
        "app": "apps.sync.main:app",
        "port": "8005",
        "static": [
            CORE_FRONTEND_EMBED,
            CORE_FRONTEND_STATIC,
            ("/sync/ui/static", "apps/sync/ui-dist"),
        ],
    },
    "office": {
        "type": "granian",
        "app": "apps.office.main:app",
        "port": "8008",
        "static": [
            CORE_FRONTEND_EMBED,
            CORE_FRONTEND_STATIC,
            ("/documents/ui/static", "apps/office/ui-dist"),
        ],
    },
    "worktracker": {
        "type": "granian",
        "app": "apps.worktracker.main:app",
        "port": "8021",
        "static": [
            CORE_FRONTEND_EMBED,
            CORE_FRONTEND_STATIC,
            ("/worktracker/ui/static", "apps/worktracker/ui-dist"),
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
            CORE_FRONTEND_EMBED,
            CORE_FRONTEND_STATIC,
            ("/wiki/ui/static", "apps/wiki/ui-dist"),
        ],
    },
    "stock": {
        "type": "granian",
        "app": "apps.stock.main:app",
        "port": "8026",
        "static": [
            CORE_FRONTEND_EMBED,
            CORE_FRONTEND_STATIC,
            ("/stock/ui/static", "apps/stock/ui-dist"),
        ],
    },
    "shop": {
        "type": "granian",
        "app": "apps.shop.main:app",
        "port": "8027",
        "static": [
            CORE_FRONTEND_EMBED,
            CORE_FRONTEND_STATIC,
            ("/shop/ui/static", "apps/shop/ui-dist"),
        ],
    },
    "geo": {
        "type": "granian",
        "app": "apps.geo.main:app",
        "port": "8028",
        "static": [
            CORE_FRONTEND_EMBED,
            CORE_FRONTEND_STATIC,
        ],
    },
    "guest_runtime": {
        "type": "granian",
        "app": "apps.guest_runtime.main:app",
        "port": "8024",
    },
    "realtime": {
        "type": "granian",
        "app": "apps.realtime.main:app",
        "port": "8025",
    },
    "redis-realtime": {
        "type": "centrifugo-compose",
        "compose_service": "redis-realtime",
    },
    "centrifugo": {
        "type": "centrifugo-compose",
        "compose_service": "centrifugo",
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
            CORE_FRONTEND_EMBED,
            CORE_FRONTEND_STATIC,
            ("/litserve/ui/static", "apps/provider_litserve/ui-dist"),
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
        "worker_app": "apps.flows.worker:worker_app",
        "workers": "1",
    },
    "rag_worker": {
        "type": "taskiq-worker",
        "worker_app": "apps.rag.worker:worker_app",
        "workers": "1",
    },
    "search_worker": {
        "type": "taskiq-worker",
        "worker_app": "apps.search.worker:worker_app",
        "workers": "2",
    },
    "sync_worker": {
        "type": "taskiq-worker",
        "worker_app": "apps.sync.worker:worker_app",
        "workers": "1",
    },
    "stock_worker": {
        "type": "taskiq-worker",
        "worker_app": "apps.stock.worker:worker_app",
        "workers": "1",
    },
    "shop_worker": {
        "type": "taskiq-worker",
        "worker_app": "apps.shop.worker:worker_app",
        "workers": "1",
    },
    "geo_worker": {
        "type": "taskiq-worker",
        "worker_app": "apps.geo.worker:worker_app",
        "workers": "1",
    },
    "crm_worker": {
        "type": "taskiq-worker",
        "worker_app": "apps.crm.worker:worker_app",
        "workers": "1",
    },
    "crm_summary_worker": {
        "type": "taskiq-worker",
        "worker_app": "apps.crm.worker_summary:worker_app",
        "workers": "1",
    },
    "idle_worker": {
        "type": "taskiq-worker",
        "worker_app": "apps.idle.worker:worker_app",
        "workers": "1",
    },
    "a2a_push_worker": {
        "type": "taskiq-worker",
        "worker_app": "apps.idle.worker_a2a_push:worker_app",
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

# watchfiles в granian следит за всеми файлами: UI-исходники и бандлы (esbuild watch пишет ui-dist)
# не перезапускают Python-процессы.
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
    "ui",
    "ui-dist",
    "embed-dist",
    "static",
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
    # venv-python напрямую: промежуточный `uv run` — лишнее звено между mprocs и
    # сервисом; mprocs убивает только верхний процесс цепочки, всё ниже сиротеет.
    venv_python = project_root / ".venv/bin/python"
    if venv_python.is_file():
        return [str(venv_python), "-u", "-m"]
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
                raise SystemExit(f"{service}: нет каталога статики {mount} — выполните make ui-build")
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
    if service_type == "npm-script":
        script = config.get("script")
        if not isinstance(script, str) or not script:
            raise ValueError(f"SERVICES[{service!r}].script must be non-empty str")
        return ["npm", "run", script]
    if service_type == "centrifugo-compose":
        compose_service = config.get("compose_service")
        if not isinstance(compose_service, str) or not compose_service:
            raise ValueError(f"SERVICES[{service!r}].compose_service must be non-empty str")
        compose_file = str(project_root / "deploy/centrifugo/docker-compose.yml")
        return [
            "docker",
            "compose",
            "-f",
            compose_file,
            "up",
            "--abort-on-container-exit",
            compose_service,
        ]
    raise ValueError(f"Неизвестный тип сервиса: {service_type}")


_PROXY_BYPASS_HOSTS = ("127.0.0.1", "localhost", "::1")


def _merge_no_proxy(existing: str) -> str:
    hosts = [h.strip() for h in existing.split(",") if h.strip()]
    hosts.extend(h for h in _PROXY_BYPASS_HOSTS if h not in hosts)
    return ",".join(hosts)


def build_env(service: str) -> dict[str, str]:
    cfg = SERVICES.get(service) or {}
    extra = cfg.get("env") or {}
    if not isinstance(extra, dict):
        raise ValueError(f"SERVICES[{service!r}].env must be dict[str,str]")
    out = dict(os.environ)
    for k, v in extra.items():
        out[str(k)] = str(v)
    no_proxy = _merge_no_proxy(out.get("NO_PROXY") or out.get("no_proxy") or "")
    out["NO_PROXY"] = no_proxy
    out["no_proxy"] = no_proxy
    if cfg.get("type") == "centrifugo-compose":
        from core.config import get_settings

        settings = get_settings()
        jwt_secret = settings.auth.jwt_secret_key
        if jwt_secret is None or not jwt_secret.strip():
            raise ValueError("auth.jwt_secret_key is required for Centrifugo")
        api_key = settings.realtime.centrifugo_api_key
        if api_key is None or not api_key.strip():
            raise ValueError("realtime.centrifugo_api_key is required")
        out["CENTRIFUGO_CLIENT_TOKEN_HMAC_SECRET_KEY"] = jwt_secret.strip()
        out["CENTRIFUGO_HTTP_API_KEY"] = api_key.strip()
    return out


def _http_ports() -> list[str]:
    return [str(cfg["port"]) for cfg in SERVICES.values() if cfg["type"] == "granian"]


def _own_tree_pids() -> set[int]:
    """Свой pid и цепочка предков: pgrep-паттерны совпадают и с нашей командой."""
    out = {os.getpid()}
    pid = os.getppid()
    while pid > 1 and pid not in out:
        out.add(pid)
        listed = subprocess.run(
            ["ps", "-o", "ppid=", "-p", str(pid)],
            capture_output=True,
            text=True,
            check=False,
        )
        raw = listed.stdout.strip()
        pid = int(raw) if raw.isdigit() else 0
    return out


def _kill_pids(pids: list[int], *, exclude: set[int]) -> list[int]:
    killed: list[int] = []
    for pid in pids:
        if pid in exclude:
            continue
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            continue
        killed.append(pid)
    return killed


def kill_port(port: str) -> None:
    listed = subprocess.run(
        ["lsof", "-ti", f":{port}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if listed.returncode != 0 or not listed.stdout.strip():
        return
    pids = [int(p) for p in listed.stdout.strip().split()]
    for pid in _kill_pids(pids, exclude=_own_tree_pids()):
        print(f"Освобождён порт {port}: завершён PID {pid}", flush=True)


# Командные сигнатуры процессов стека: mprocs рестартует/останавливает только
# верхний процесс, поэтому сироты старых поколений добиваем при старте.
_ORPHAN_CMD_PATTERNS = (
    # NB: паттерн не должен начинаться с '-': pgrep примет его за опцию.
    r"granian --interface asgi apps\.",
    r"taskiq (worker|scheduler) apps\.",
    r"scripts\.dev\.run ",
    r"scripts/build/ui\.ts --dev --watch",
    r"litserve",
    r"deploy/centrifugo/docker-compose\.yml up",
)


def kill_orphans() -> None:
    """SIGKILL всем сиротам стека: держатели портов + процессы прошлых запусков."""
    exclude = _own_tree_pids()
    killed: list[int] = []
    for pattern in _ORPHAN_CMD_PATTERNS:
        listed = subprocess.run(
            ["pgrep", "-f", pattern],
            capture_output=True,
            text=True,
            check=False,
        )
        if listed.returncode != 0 or not listed.stdout.strip():
            continue
        pids = [int(p) for p in listed.stdout.strip().split()]
        for pid in _kill_pids(pids, exclude=exclude):
            killed.append(pid)
    if killed:
        print(f"Завершены процессы прошлых запусков: {sorted(set(killed))}", flush=True)
    for port in _http_ports():
        kill_port(port)


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
                f"Неизвестный сервис для исключения: {name}. Доступно: {', '.join(SERVICES.keys())}",
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
    # --from-make-kill/--kill/APP_KILL: флаги оставлены для совместимости,
    # зачистка сирот выполняется при каждом старте стека.
    if rest and rest[-1] == "--from-make-kill":
        rest = rest[:-1]
    if "--kill" in rest:
        rest = [t for t in rest if t != "--kill"]
    kill_orphans()
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
        "# Generated by scripts/dev/run.py (APP_EXCLUDE / --ex).",
        "procs:",
    ]
    for name in names:
        lines.append(f"  {_mprocs_proc_key(name)}:")
        lines.append(
            f'    shell: "exec .venv/bin/python -m scripts.dev.run {name}"'
        )
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
        print("Использование: python -m scripts.dev.run <service>")
        print(
            f"Доступные сервисы: {', '.join(SERVICES.keys())}, all, from-make, kill-ports"
        )
        sys.exit(1)

    service = sys.argv[1]

    if service == "kill-ports":
        kill_orphans()
        return

    # OpenFGA обязателен для локальных app-процессов (как Postgres).
    if service in ("from-make", "all") or service in SERVICES:
        from scripts.dev.openfga_env_bootstrap import require_dev_openfga_env

        _ = require_dev_openfga_env()

    if service == "from-make":
        _run_from_make()
        return

    if service == "all":
        rest = sys.argv[2:]
        kill_orphans()
        exclude = _parse_exclude_from_argv(rest) | _exclude_from_env()
        _validate_exclude(exclude)
        run_all(exclude=exclude)
        return

    if service not in SERVICES:
        print(f"Неизвестный сервис: {service}")
        print(f"Доступные: {', '.join(SERVICES.keys())}, all, from-make, kill-ports")
        sys.exit(1)

    port = str(SERVICES[service].get("port") or "")
    if port:
        kill_port(port)
    cmd = build_command(service)
    print(f"Запуск {service}: {' '.join(cmd)}", flush=True)
    env = build_env(service)
    if "debugpy" in sys.modules or "pydevd" in sys.modules:
        # Под дебагером exec уничтожит обёртку debugpy/pydevd — запускаем child.
        result = subprocess.run(cmd, cwd=str(project_root), env=env)
        sys.exit(result.returncode)
    # exec: dev-процесс становится сервисом — mprocs убивает именно его,
    # и сервисный мастер сам репит своих worker'ов (иначе остаются сироты).
    os.execvpe(cmd[0], cmd, env)


if __name__ == "__main__":
    main()
