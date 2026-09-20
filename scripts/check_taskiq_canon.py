#!/usr/bin/env python3
"""CI-gate единого TaskIQ-паттерна платформы.

Проверяет:
1. Статически: нет ``@broker.task``, прямых ``.kiq(``, ``find_task(``,
   ``AsyncKicker(``, ``create_broker(`` вне whitelist в ``apps/`` и ``core/``.
2. Статически: нет ``*_TASK_NAME = declare_task`` (Spec ≠ str-имя).
3. Статически: идентификатор Spec не передаётся в ``task_name=`` / ``==`` / ``!=``
   без ``.name``.
4. Runtime после ``wire_all()``: все ``TaskSpec`` snake_case и уникальны;
   каждая очередь из реестра имеет брокер; **каждая** задача зарегистрирована
   на брокере своей очереди; string ``task_name="…"`` в bootstrap/schedule
   ⊆ ``{spec.name}``.

Запуск:
    uv run python scripts/check_taskiq_canon.py
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SCAN_ROOTS: tuple[Path, ...] = (REPO_ROOT / "apps", REPO_ROOT / "core")
TEST_ROOT = REPO_ROOT / "tests"

SKIP_DIR_NAMES: frozenset[str] = frozenset({"vendor", "__pycache__", ".git"})

# Относительные пути (posix), где легитимны низкоуровневые TaskIQ-примитивы.
KIQ_ALLOWLIST: frozenset[str] = frozenset(
    {
        "core/tasks/kicker.py",
        "core/tasks/logging_middleware.py",
        "apps/scheduler/dispatch.py",
        "core/scheduler/service.py",
    }
)

FIND_TASK_ALLOWLIST: frozenset[str] = frozenset(
    {
        "apps/scheduler/dispatch.py",
    }
)

ASYNC_KICKER_ALLOWLIST: frozenset[str] = frozenset(
    {
        "core/tasks/kicker.py",
        "apps/scheduler/dispatch.py",
        "core/scheduler/service.py",
    }
)

CREATE_BROKER_ALLOWLIST: frozenset[str] = frozenset(
    {
        "core/tasks/broker.py",
        "apps/flows_worker/broker.py",
        "apps/idle_worker/broker.py",
        "apps/rag_worker/broker.py",
        "apps/crm_worker/broker.py",
        "apps/crm_worker/summary_broker.py",
        "apps/search_worker/broker.py",
        "apps/sync/realtime/broker.py",
    }
)

# Файлы, где ``task_name="literal"`` обязан быть именем из реестра TaskSpec.
SCHEDULE_LITERAL_SCAN_PATHS: frozenset[str] = frozenset(
    {
        "apps/scheduler/main.py",
        "apps/scheduler/crawl_schedule_bootstrap.py",
        "apps/flows/src/services/schedule_service.py",
        "apps/flows/src/services/llm_models_service.py",
        "apps/crm/services/integration_auto_sync_service.py",
        "apps/crm/api/namespaces.py",
    }
)

BROKER_TASK_DECORATOR_RE = re.compile(r"@broker\.task\b")
KIQ_CALL_RE = re.compile(r"\.kiq\s*\(")
FIND_TASK_RE = re.compile(r"\.find_task\s*\(")
ASYNC_KICKER_RE = re.compile(r"\bAsyncKicker\s*\(")
CREATE_BROKER_RE = re.compile(r"\bcreate_broker\s*\(")
TASK_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
DECLARE_TASK_NAME_ASSIGN_RE = re.compile(
    r"^([A-Z][A-Z0-9_]*_TASK_NAME)\s*=\s*declare_task\s*\(",
    re.MULTILINE,
)
TASK_NAME_KWARG_SPEC_RE = re.compile(
    r"\btask_name\s*=\s*([A-Z][A-Z0-9_]*)\b(?!\s*\.)",
)
COMPARE_SPEC_RE = re.compile(
    r"(?:==|!=)\s*([A-Z][A-Z0-9_]*)\b(?!\s*\.)",
)
TASK_NAME_STRING_LITERAL_RE = re.compile(
    r"\btask_name\s*=\s*[\"']([a-z][a-z0-9_]*)[\"']",
)


def _relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _should_scan(path: Path) -> bool:
    return path.suffix == ".py" and not any(part in SKIP_DIR_NAMES for part in path.parts)


def _iter_py_files(*roots: Path) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if _should_scan(path):
                files.append(path)
    return files


def _collect_declare_task_symbols(files: list[Path]) -> set[str]:
    """Имена переменных ``X = declare_task(...)`` — это TaskSpec, не str."""
    symbols: set[str] = set()
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            if not isinstance(node.value, ast.Call):
                continue
            func = node.value.func
            if isinstance(func, ast.Name) and func.id == "declare_task":
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        symbols.add(target.id)
            elif (
                isinstance(func, ast.Attribute)
                and func.attr == "declare_task"
                and isinstance(func.value, ast.Name)
            ):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        symbols.add(target.id)
    return symbols


def _scan_forbidden() -> list[str]:
    errors: list[str] = []
    for path in _iter_py_files(*SCAN_ROOTS):
        rel = _relative(path)
        text = path.read_text(encoding="utf-8")
        if BROKER_TASK_DECORATOR_RE.search(text):
            errors.append(f"{rel}: запрещён @broker.task — используйте @platform_task(SPEC)")
        if KIQ_CALL_RE.search(text) and rel not in KIQ_ALLOWLIST:
            errors.append(
                (
                    f"{rel}: прямой .kiq(...) запрещён — используйте core.tasks.enqueue "
                    f"(whitelist: {', '.join(sorted(KIQ_ALLOWLIST))})"
                )
            )
        if FIND_TASK_RE.search(text) and rel not in FIND_TASK_ALLOWLIST:
            errors.append(f"{rel}: find_task(...) запрещён вне scheduler dispatch")
        if ASYNC_KICKER_RE.search(text) and rel not in ASYNC_KICKER_ALLOWLIST:
            errors.append(f"{rel}: AsyncKicker(...) запрещён — используйте enqueue")
        if CREATE_BROKER_RE.search(text) and rel not in CREATE_BROKER_ALLOWLIST:
            errors.append(
                f"{rel}: create_broker(...) только в core/tasks/broker.py и thin broker-модулях"
            )
        for match in DECLARE_TASK_NAME_ASSIGN_RE.finditer(text):
            errors.append(
                f"{rel}: {match.group(1)} = declare_task(...) запрещён — "
                f"Spec называйте без суффикса _TASK_NAME; str-имя = SPEC.name"
            )
    return errors


def _scan_taskspec_as_str(spec_symbols: set[str]) -> list[str]:
    """TaskSpec-символ в task_name= / == / != без .name — класс evaluation-бага."""
    errors: list[str] = []
    roots = (*SCAN_ROOTS, TEST_ROOT)
    for path in _iter_py_files(*roots):
        rel = _relative(path)
        text = path.read_text(encoding="utf-8")
        for match in TASK_NAME_KWARG_SPEC_RE.finditer(text):
            symbol = match.group(1)
            if symbol in spec_symbols:
                line = text[: match.start()].count("\n") + 1
                errors.append(
                    f"{rel}:{line}: task_name={symbol} — нужен {symbol}.name "
                    f"(TaskSpec нельзя передавать как str)"
                )
        for match in COMPARE_SPEC_RE.finditer(text):
            symbol = match.group(1)
            if symbol not in spec_symbols:
                continue
            # Разрешаем только сравнения с другим Spec / identity в registry tests.
            line_start = text.rfind("\n", 0, match.start()) + 1
            line_text = text[line_start : text.find("\n", match.start())]
            if ".name" in line_text:
                continue
            # `registered != task` в get_task_spec — сравнивает два TaskSpec, ок.
            if "TaskSpec" in line_text or "registered" in line_text:
                continue
            line = text[: match.start()].count("\n") + 1
            errors.append(
                f"{rel}:{line}: сравнение с {symbol} без .name — "
                f"str == TaskSpec всегда False"
            )
    return errors


def _check_runtime_registry() -> list[str]:
    errors: list[str] = []
    from apps.platform_tasks.wiring import all_queues, wire_all
    from core.tasks import all_task_specs, registered_queue_brokers

    wire_all()
    specs = all_task_specs()
    brokers = registered_queue_brokers()
    known_queues = set(all_queues())
    registry_names = {spec.name for spec in specs}

    if not specs:
        errors.append("registry пуст после wire_all()")
        return errors

    seen_names: set[str] = set()
    for spec in specs:
        if spec.name in seen_names:
            errors.append(f"дубликат TaskSpec.name: {spec.name!r}")
        seen_names.add(spec.name)
        if not TASK_NAME_RE.match(spec.name):
            errors.append(f"имя задачи не snake_case: {spec.name!r}")
        if spec.queue not in known_queues:
            errors.append(f"задача {spec.name!r}: очередь {spec.queue!r} не в wiring.all_queues()")
        if spec.queue not in brokers:
            errors.append(f"задача {spec.name!r}: брокер очереди {spec.queue!r} не зарегистрирован")

    for queue in known_queues:
        if queue not in brokers:
            errors.append(f"очередь {queue!r} из wiring без брокера")

    for spec in specs:
        broker = brokers.get(spec.queue)
        if broker is None or broker.find_task(spec.name) is None:
            errors.append(f"задача не на брокере очереди: {spec.queue}:{spec.name}")

    for rel in sorted(SCHEDULE_LITERAL_SCAN_PATHS):
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for match in TASK_NAME_STRING_LITERAL_RE.finditer(text):
            literal = match.group(1)
            if literal not in registry_names:
                line = text[: match.start()].count("\n") + 1
                errors.append(
                    f"{rel}:{line}: task_name={literal!r} нет в TaskSpec registry — "
                    f"используйте SPEC.name"
                )

    return errors


def main() -> int:
    app_core_files = _iter_py_files(*SCAN_ROOTS)
    spec_symbols = _collect_declare_task_symbols(app_core_files)
    errors = _scan_forbidden()
    errors.extend(_scan_taskspec_as_str(spec_symbols))
    errors.extend(_check_runtime_registry())
    if errors:
        print("check_taskiq_canon: FAIL", file=sys.stderr)
        for item in errors:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("check_taskiq_canon: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
