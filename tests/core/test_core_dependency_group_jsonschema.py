"""
Контракт зависимостей для CodeTool / json_schema_parameters.

Почему модульные тесты валидации схемы не ловили отсутствие пакета в prod:
- Локально и в CI обычно `uv sync` с default-groups, в т.ч. группа `dev` → schemathesis
  тянет `jsonschema` транзитивно, импорт в `validate_tool_args_against_parameters_schema` работает.
- Образ приложения (см. Dockerfile) ставит зависимости через `uv export --frozen --no-dev`
  и набор групп (`core`, `agents`, …) — без dev транзитивы из schemathesis не попадают в образ.
- FastAPI не объявляет `jsonschema` как свою прямую зависимость, значит пакет должен быть
  явно в группе `core` (или другой группе, попадающей в export prod).
"""

from __future__ import annotations

import tomllib
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_core_dependency_group_lists_jsonschema() -> None:
    pyproject_path = _repo_root() / "pyproject.toml"
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    groups = data.get("dependency-groups")
    if not isinstance(groups, dict):
        raise AssertionError("pyproject.toml: missing [dependency-groups]")
    core = groups.get("core")
    if not isinstance(core, list):
        raise AssertionError("pyproject.toml: dependency-groups.core must be a list")

    jsonschema_pins = [d for d in core if isinstance(d, str) and d.startswith("jsonschema")]
    assert jsonschema_pins, (
        "В [dependency-groups].core должна быть прямая зависимость `jsonschema`: "
        "`apps/flows/src/tools/json_schema_parameters.py` импортирует её для CodeTool. "
        "Prod Docker: uv export --no-dev — без явной записи пакет не попадёт в образ."
    )
