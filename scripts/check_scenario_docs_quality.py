"""Quality gate для docs/scenarios: шаги, скриншоты, taxonomy, pytest markers."""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from scenario_taxonomy import DEFAULT_SCENARIO_TAG, load_scenario_taxonomy, validate_service_tag

_STEP_HEADING_RE = re.compile(r"^##\s+Шаг\b", re.MULTILINE)
_MIN_STEPS = 2
_UI_E2E_ROOT = Path("tests/ui/e2e")


@dataclass(frozen=True)
class ScenarioMarker:
    service: str
    tag: str
    doc_slug: str | None
    source_file: Path
    test_name: str


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _slug_readme_dirs(scenarios_root: Path) -> list[Path]:
    slug_dirs: list[Path] = []
    for service_dir in sorted(p for p in scenarios_root.iterdir() if p.is_dir() and not p.name.startswith(".")):
        for tag_dir in sorted(p for p in service_dir.iterdir() if p.is_dir() and not p.name.startswith(".")):
            for slug_dir in sorted(p for p in tag_dir.iterdir() if p.is_dir() and not p.name.startswith(".")):
                if (slug_dir / "README.md").is_file():
                    slug_dirs.append(slug_dir)
    return slug_dirs


def _count_steps(readme: Path) -> int:
    text = readme.read_text(encoding="utf-8")
    return len(_STEP_HEADING_RE.findall(text))


def _has_screenshot(readme_dir: Path) -> bool:
    shots = readme_dir / "screenshots"
    if not shots.is_dir():
        return False
    return any(p.suffix.lower() == ".png" for p in shots.iterdir() if p.is_file())


def _title_from_readme(readme: Path) -> str:
    for line in readme.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            if title:
                return title
    return ""


def _parse_scenario_markers(tests_root: Path) -> list[ScenarioMarker]:
    markers: list[ScenarioMarker] = []
    for path in sorted(tests_root.rglob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
                continue
            if not node.name.startswith("test_"):
                continue
            for dec in node.decorator_list:
                if not isinstance(dec, ast.Call):
                    continue
                func = dec.func
                if not isinstance(func, ast.Attribute):
                    continue
                if not isinstance(func.value, ast.Attribute):
                    continue
                if func.value.attr != "mark" or func.attr != "scenario":
                    continue
                kwargs = {kw.arg: kw.value for kw in dec.keywords if kw.arg is not None}
                service = _ast_str(kwargs.get("service"))
                tag = _ast_str(kwargs.get("tag")) or DEFAULT_SCENARIO_TAG
                doc_slug = _ast_str(kwargs.get("doc_slug"))
                if service is None:
                    raise ValueError(f"{path}:{node.lineno} @pytest.mark.scenario без service=...")
                markers.append(
                    ScenarioMarker(
                        service=service,
                        tag=tag,
                        doc_slug=doc_slug,
                        source_file=path,
                        test_name=node.name,
                    )
                )
    return markers


def _ast_str(node: ast.expr | None) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        value = node.value.strip()
        return value if value else None
    return None


def _check_readme_quality(scenarios_root: Path) -> list[str]:
    errors: list[str] = []
    for slug_dir in _slug_readme_dirs(scenarios_root):
        readme = slug_dir / "README.md"
        rel = slug_dir.relative_to(scenarios_root.parent)
        title = _title_from_readme(readme)
        if not title:
            errors.append(f"{rel}: README.md без заголовка #")
        step_count = _count_steps(readme)
        if step_count < _MIN_STEPS:
            errors.append(
                f"{rel}: нужно минимум {_MIN_STEPS} секций «## Шаг …», найдено {step_count}"
            )
        if not _has_screenshot(slug_dir):
            errors.append(f"{rel}: нет screenshots/*.png")
    return errors


def _check_taxonomy_markers(repo_root: Path) -> tuple[list[str], list[str]]:
    taxonomy = load_scenario_taxonomy(repo_root)
    errors: list[str] = []
    warnings: list[str] = []

    markers = _parse_scenario_markers(repo_root / _UI_E2E_ROOT)
    used_tags: set[tuple[str, str]] = set()
    for marker in markers:
        try:
            validate_service_tag(taxonomy, marker.service, marker.tag)
        except ValueError as exc:
            errors.append(f"{marker.source_file}: {marker.test_name}: {exc}")
        used_tags.add((marker.service, marker.tag))

    for service, spec in taxonomy.services.items():
        for tag_key in spec.tags:
            if (service, tag_key) not in used_tags:
                warnings.append(
                    f"taxonomy: services.{service}.tags.{tag_key} не используется ни одним @pytest.mark.scenario"
                )

    return errors, warnings


def _find_slug_readme(repo_root: Path, service: str, slug: str) -> bool:
    service_root = repo_root / "docs" / "scenarios" / service
    if not service_root.is_dir():
        return False
    for tag_dir in service_root.iterdir():
        if not tag_dir.is_dir() or tag_dir.name.startswith("."):
            continue
        candidate = tag_dir / slug / "README.md"
        if candidate.is_file():
            return True
    return False


def _check_learning_path_hrefs(repo_root: Path) -> list[str]:
    taxonomy = load_scenario_taxonomy(repo_root)
    errors: list[str] = []
    for path in taxonomy.learning_paths:
        for step in path.steps:
            href = step.href.rstrip("/")
            if href.startswith("scenarios/"):
                parts = href.split("/")
                if len(parts) < 3:
                    errors.append(f"learning_paths.{path.path_id}: некорректный href {step.href!r}")
                    continue
                service = parts[1]
                slug = parts[2]
                if not _find_slug_readme(repo_root, service, slug):
                    errors.append(
                        f"learning_paths.{path.path_id}: href {step.href!r} — нет README.md для slug {slug!r}"
                    )
            elif href == "quickstart":
                if not (repo_root / "docs" / "quickstart.md").is_file():
                    errors.append(f"learning_paths.{path.path_id}: нет docs/quickstart.md")
            elif href == "api":
                continue
            else:
                errors.append(f"learning_paths.{path.path_id}: неизвестный href {step.href!r}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Проверка качества docs/scenarios")
    parser.add_argument(
        "--warnings-ok",
        action="store_true",
        help="Не падать на предупреждения taxonomy (orphan tags)",
    )
    args = parser.parse_args()

    repo_root = _repo_root()
    scenarios_root = repo_root / "docs" / "scenarios"
    if not scenarios_root.is_dir():
        print(f"Нет каталога {scenarios_root}", file=sys.stderr)
        return 1

    errors: list[str] = []
    warnings: list[str] = []

    errors.extend(_check_readme_quality(scenarios_root))
    marker_errors, marker_warnings = _check_taxonomy_markers(repo_root)
    errors.extend(marker_errors)
    warnings.extend(marker_warnings)
    errors.extend(_check_learning_path_hrefs(repo_root))

    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)

    if errors:
        print("Ошибки качества документации сценариев:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    if warnings and not args.warnings_ok:
        print(
            f"FAIL: {len(warnings)} предупреждений taxonomy (orphan tags). "
            "Исправьте taxonomy или добавьте --warnings-ok.",
            file=sys.stderr,
        )
        return 1

    print("check_scenario_docs_quality: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
