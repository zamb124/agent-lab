#!/usr/bin/env python3
"""
CI-gate: сервисы не импортируют друг друга.

Разрешено всегда:
- `apps/<svc>_worker/**` → `apps.<svc>.*` (воркер — часть владельца);
- `apps.<x>.tasks.task_names` / `apps.<x>_worker.tasks.task_names` из любого сервиса
  (declare_task + enqueue — единственный контракт постановки задачи);
- `apps.worker_manifest` из воркеров и scheduler (модуль без HTTP-процесса);
- репозитории и доменные модели владельца (`apps.<svc>.db.*`, `apps.<svc>.models.*`,
  `apps.flows.src.db.*`, `apps.flows.src.models.*`) — канон межсервисного доступа к данным
  при доступной БД peer-домена (architecture.mdc);
- библиотечные домены без HTTP-процесса (`apps.agent`, `apps.worker_manifest`): их можно
  импортировать из хостов, сами они не импортируют ни один сервис.

Любое другое ребро `apps/<a> → apps/<b>` (services, config, dependencies, api,
runtime) — FAIL: общий код уезжает в `core/`, владелец подключается через `core/clients`.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
APPS_ROOT = REPO_ROOT / "apps"
SKIP_DIR_NAMES: frozenset[str] = frozenset({"vendor", "__pycache__", "desktop"})
LIBRARY_DOMAINS: frozenset[str] = frozenset({"agent", "worker_manifest"})


def _service_of(path: Path) -> str:
    return path.relative_to(APPS_ROOT).parts[0]


def _imported_apps_modules(tree: ast.AST) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("apps."):
            modules.append(node.module)
        elif isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names if alias.name.startswith("apps."))
    return modules


def _is_peer_data_module(module: str) -> bool:
    parts = module.split(".")
    layer_index = 3 if len(parts) > 3 and parts[2] == "src" else 2
    return len(parts) > layer_index and parts[layer_index] in {"db", "models"}


def _always_allowed(source_service: str, module: str) -> bool:
    target_service = module.split(".")[1]
    if source_service.endswith("_worker") and source_service[: -len("_worker")] == target_service:
        return True
    if module.endswith(".tasks.task_names"):
        return True
    if target_service in LIBRARY_DOMAINS:
        return True
    return _is_peer_data_module(module)


def collect_edges() -> set[str]:
    edges: set[str] = set()
    for path in sorted(APPS_ROOT.rglob("*.py")):
        if SKIP_DIR_NAMES & set(path.parts):
            continue
        source_service = _service_of(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for module in _imported_apps_modules(tree):
            target_service = module.split(".")[1]
            if target_service == source_service or _always_allowed(source_service, module):
                continue
            edges.add(f"{path.relative_to(REPO_ROOT).as_posix()} -> {module}")
    return edges


def main() -> int:
    edges = sorted(collect_edges())
    if edges:
        print("check_cross_service_imports: FAIL — импорты между сервисами:")
        for edge in edges:
            print(f"  {edge}")
        print("Вынеси общий код в core/ или подключай владельца через core/clients (architecture.mdc).")
        return 1
    print("check_cross_service_imports: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
