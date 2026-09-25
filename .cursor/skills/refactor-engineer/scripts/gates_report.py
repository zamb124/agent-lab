#!/usr/bin/env python3
"""Все шаги `make lint` без остановки на первом падении.

Шаги читаются из `mk/lint.mk` (рецепты `_lint-py` и `lint-ts`) и `Makefile`
(зависимости `check-events-canon`), поэтому список не расходится с `make lint`.
Каждый шаг запускается отдельно; лог шага — `<out>/<NN>_<name>.log`, сводка —
stdout и `<out>/summary.txt`. Выход 1, если упал хотя бы один шаг.

Запуск: `uv run python .cursor/skills/refactor-engineer/scripts/gates_report.py [<out_dir>]`.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
LINT_MK = REPO / "mk" / "lint.mk"
MAKEFILE = REPO / "Makefile"
VARIABLES = {
    "$(RUFF_CHECK_ARGS)": "apps core",
    "$(BASEDPYRIGHT_CHECK_ARGS)": "--level warning --warnings apps core",
    "$(PYTHON_CHECK_PATHS)": "apps core",
}
MAKE_CALL = re.compile(r"^\$\(MAKE\)\s+--no-print-directory\s+([\w.-]+)$")


def recipe(makefile: Path, target: str) -> list[str]:
    commands: list[str] = []
    inside = False
    for line in makefile.read_text(encoding="utf-8").splitlines():
        if re.match(rf"^{re.escape(target)}:", line):
            inside = True
            continue
        if not inside:
            continue
        if line.startswith("\t"):
            commands.append(line.strip())
        elif line.strip() == "":
            continue
        else:
            break
    if not commands:
        raise SystemExit(f"{makefile}: рецепт {target} не найден")
    return commands


def dependencies(makefile: Path, target: str) -> list[str]:
    for line in makefile.read_text(encoding="utf-8").splitlines():
        match = re.match(rf"^{re.escape(target)}:\s*(.*)$", line)
        if match:
            return match.group(1).split()
    raise SystemExit(f"{makefile}: цель {target} не найдена")


def normalize(command: str) -> str:
    command = command.lstrip("@")
    for variable, value in VARIABLES.items():
        command = command.replace(variable, value)
    return command


def step_name(command: str) -> str:
    script = re.search(r"([\w-]+)\.(py|sh)\b", command)
    if script:
        return script.group(1)
    target = re.search(r"make --no-print-directory ([\w.-]+)", command)
    if target:
        return target.group(1)
    return re.sub(r"\W+", "_", command)[:40]


def steps() -> list[str]:
    commands: list[str] = []
    for raw in recipe(LINT_MK, "_lint-py"):
        command = normalize(raw)
        if command.startswith("echo"):
            continue
        commands.append(command)
    for raw in recipe(LINT_MK, "lint-ts"):
        command = normalize(raw)
        if command.startswith("echo"):
            continue
        call = MAKE_CALL.match(command)
        if call and call.group(1) == "check-events-canon":
            commands.extend(f"make --no-print-directory {dep}" for dep in dependencies(MAKEFILE, "check-events-canon"))
        elif call:
            commands.append(f"make --no-print-directory {call.group(1)}")
        else:
            commands.append(command)
    return commands


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/refactor_gates")
    out.mkdir(parents=True, exist_ok=True)
    summary: list[str] = []
    failed = 0
    for index, command in enumerate(steps(), 1):
        name = f"{index:02d}_{step_name(command)}"
        completed = subprocess.run(command, shell=True, cwd=REPO, capture_output=True, text=True, check=False)
        (out / f"{name}.log").write_text(f"$ {command}\n{completed.stdout}{completed.stderr}", encoding="utf-8")
        status = "OK  " if completed.returncode == 0 else "FAIL"
        failed += completed.returncode != 0
        summary.append(f"{status} {name}  ({command})")
        print(summary[-1], flush=True)
    (out / "summary.txt").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print(f"--- шагов: {len(summary)}, упало: {failed}, логи: {out}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
