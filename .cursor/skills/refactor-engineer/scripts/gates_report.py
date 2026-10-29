"""Все шаги `make lint` без остановки на первом падении.

Гейты берутся из `python -m scripts.gates --list` (сьюты `lint` и `lint_ts`).
ruff, basedpyright, analyze_imports и tsc — отдельные шаги, как в `mk/lint.mk`.
Каждый шаг запускается отдельно; лог — `<out>/<NN>_<name>.log`, сводка — stdout
и `<out>/summary.txt`. Выход 1, если упал хотя бы один шаг.

Запуск: `uv run python .cursor/skills/refactor-engineer/scripts/gates_report.py [<out_dir>]`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]

FIXED = (
    ("ruff", ["uv", "run", "ruff", "check", "apps", "core"]),
    ("basedpyright", ["uv", "run", "basedpyright", "--level", "warning", "--warnings", "apps", "core"]),
    ("analyze_imports", ["uv", "run", "python", "analyze_imports.py"]),
    ("tsc", ["npx", "tsc", "-p", "tsconfig.json"]),
)


def gate_steps() -> list[tuple[str, list[str]]]:
    completed = subprocess.run(
        [sys.executable, "-m", "scripts.gates", "--list"],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    )
    steps: list[tuple[str, list[str]]] = []
    for line in completed.stdout.splitlines():
        name, suites, command = line.split("\t")
        if not ({"lint", "lint_ts"} & set(filter(None, suites.split(",")))):
            continue
        argv = command.split()
        if argv[0] == "python":
            argv[0] = sys.executable
        steps.append((name.replace(".", "_"), argv))
    return steps


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/refactor_gates")
    out.mkdir(parents=True, exist_ok=True)
    summary: list[str] = []
    failed = 0
    steps = [*FIXED, *gate_steps()]
    for index, (name, argv) in enumerate(steps, 1):
        label = f"{index:02d}_{name}"
        completed = subprocess.run(argv, cwd=REPO, capture_output=True, text=True, check=False)
        (out / f"{label}.log").write_text(
            f"$ {' '.join(argv)}\n{completed.stdout}{completed.stderr}",
            encoding="utf-8",
        )
        status = "OK  " if completed.returncode == 0 else "FAIL"
        failed += completed.returncode != 0
        summary.append(f"{status} {label}")
        print(summary[-1], flush=True)
    (out / "summary.txt").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print(f"--- шагов: {len(summary)}, упало: {failed}, логи: {out}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
