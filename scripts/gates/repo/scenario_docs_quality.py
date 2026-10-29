"""Quality gate для docs/scenarios: шаги, плоские PNG, taxonomy, pytest markers."""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from scripts.docs.scenario_taxonomy import (
    DEFAULT_SCENARIO_TAG,
    load_scenario_taxonomy,
    validate_service_tag,
)

_STEP_HEADING_RE = re.compile(r"^##\s+Шаг\b", re.MULTILINE)
_EN_STEP_HEADING_RE = re.compile(r"^##\s+Step\b", re.MULTILINE)
_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
_IMAGE_LINK_RE = re.compile(r"!\[[^\]]*\]\(([^)]+\.png)\)")
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
    return Path(__file__).resolve().parents[3]


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


def _image_links(readme: Path) -> list[str]:
    return _IMAGE_LINK_RE.findall(readme.read_text(encoding="utf-8"))


def _check_screenshot_layout(slug_dir: Path, readme: Path, scenarios_root: Path) -> list[str]:
    """PNG должны лежать рядом с README и иметь имя `<slug>--<NN>-<meaning>.png`."""
    errors: list[str] = []
    slug = slug_dir.name
    legacy_dir = slug_dir / "screenshots"
    if legacy_dir.exists():
        errors.append("legacy-каталог screenshots/ запрещён; PNG должны лежать рядом с README.md")

    refs = _image_links(readme)
    if not refs:
        errors.append("README.md не содержит ссылок на PNG-скриншоты")
        return errors

    filename_re = re.compile(
        rf"^{re.escape(slug)}--\d{{2,}}-[a-z0-9]+(?:-[a-z0-9]+)*\.png$"
    )
    referenced_names: set[str] = set()
    for target in refs:
        target_path = Path(target)
        if target_path.is_absolute() or len(target_path.parts) != 1:
            errors.append(
                f"скриншот {target!r} должен лежать рядом с README.md без подкаталога"
            )
            continue
        filename = target_path.name
        referenced_names.add(filename)
        if filename_re.fullmatch(filename) is None:
            errors.append(
                f"имя {filename!r} не соответствует {slug}--<номер>-<понятное-имя>.png"
            )
        if not (slug_dir / filename).is_file():
            errors.append(f"README.md ссылается на отсутствующий файл {filename!r}")

    flat_pngs = {p.name for p in slug_dir.glob("*.png") if p.is_file()}
    for filename in sorted(flat_pngs - referenced_names):
        errors.append(f"PNG {filename!r} не используется в README.md")

    en_readme = slug_dir / "README.en.md"
    if en_readme.is_file() and _image_links(en_readme) != refs:
        errors.append("README.en.md должен ссылаться на те же PNG и в том же порядке")
    errors.extend(_check_en_readme(slug_dir, scenarios_root))
    return errors


def _title_from_readme(readme: Path) -> str:
    for line in readme.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            if title:
                return title
    return ""


def _en_step_headings(readme: Path) -> list[str]:
    text = readme.read_text(encoding="utf-8")
    headings: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if _EN_STEP_HEADING_RE.match(stripped):
            headings.append(stripped.split(".", 1)[-1].strip())
    return headings


def _check_en_readme(slug_dir: Path, scenarios_root: Path) -> list[str]:
    if _is_ui_kit_scenario_stub(slug_dir, scenarios_root):
        return []
    errors: list[str] = []
    rel = slug_dir.relative_to(scenarios_root.parent)
    en_readme = slug_dir / "README.en.md"
    if not en_readme.is_file():
        errors.append(f"{rel}: отсутствует README.en.md")
        return errors
    title = _title_from_readme(en_readme)
    if not title:
        errors.append(f"{rel}: README.en.md без заголовка #")
    elif _CYRILLIC_RE.search(title):
        errors.append(f"{rel}: README.en.md title содержит кириллицу")
    for heading in _en_step_headings(en_readme):
        if _CYRILLIC_RE.search(heading):
            errors.append(f"{rel}: README.en.md step heading содержит кириллицу: {heading[:80]!r}")
    return errors


def _scenario_step_calls(node: ast.AsyncFunctionDef | ast.FunctionDef) -> list[ast.Call]:
    calls: list[ast.Call] = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if not isinstance(func, ast.Attribute) or func.attr != "step":
            continue
        if not isinstance(func.value, ast.Name) or func.value.id != "scenario":
            continue
        calls.append(child)
    return calls


def _check_scenario_marker_en_fields(tests_root: Path) -> list[str]:
    errors: list[str] = []
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
                if "title_en" not in kwargs:
                    errors.append(f"{path}:{node.lineno} {node.name}: @pytest.mark.scenario без title_en")
                if "description_en" not in kwargs:
                    errors.append(
                        f"{path}:{node.lineno} {node.name}: @pytest.mark.scenario без description_en"
                    )
                for step_call in _scenario_step_calls(node):
                    step_kwargs = {kw.arg: kw.value for kw in step_call.keywords if kw.arg is not None}
                    if "label_en" not in step_kwargs:
                        errors.append(
                            f"{path}:{step_call.lineno} {node.name}: scenario.step без label_en"
                        )
                    if "details" in step_kwargs and "details_en" not in step_kwargs:
                        errors.append(
                            f"{path}:{step_call.lineno} {node.name}: scenario.step с details без details_en"
                        )
    return errors


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


def _is_ui_kit_scenario_stub(slug_dir: Path, scenarios_root: Path) -> bool:
    """UI Kit pages sync from tests/ui/design-system; full scenario quality — только после make ui-doc."""
    try:
        parts = slug_dir.relative_to(scenarios_root).parts
    except ValueError:
        return False
    return len(parts) >= 2 and parts[0] == "platform" and parts[1] == "ui-kit"


def check_readme_quality(scenarios_root: Path) -> list[str]:
    errors: list[str] = []
    for slug_dir in _slug_readme_dirs(scenarios_root):
        if _is_ui_kit_scenario_stub(slug_dir, scenarios_root):
            continue
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
        for screenshot_error in _check_screenshot_layout(slug_dir, readme, scenarios_root):
            errors.append(f"{rel}: {screenshot_error}")
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
    tag_hub = service_root / slug / "README.md"
    if tag_hub.is_file():
        return True
    for tag_dir in service_root.iterdir():
        if not tag_dir.is_dir() or tag_dir.name.startswith("."):
            continue
        candidate = tag_dir / slug / "README.md"
        if candidate.is_file():
            return True
    return False


def _check_learning_path_hrefs(repo_root: Path) -> list[str]:
    """Публичный канон: scenarios/<service>/<slug>/ — без уровня tag из репозитория."""
    taxonomy = load_scenario_taxonomy(repo_root)
    errors: list[str] = []
    for path in taxonomy.learning_paths:
        for step in path.steps:
            href = step.href.rstrip("/")
            if href.startswith("scenarios/"):
                parts = href.split("/")
                if len(parts) != 3 or not parts[1] or not parts[2]:
                    errors.append(
                        f"learning_paths.{path.path_id}: href {step.href!r} — "
                        "ожидается scenarios/<service>/<slug>/ (без tag)"
                    )
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


@dataclass(frozen=True)
class _CliArgs:
    warnings_ok: bool


def _parse_cli_args(argv: list[str] | None = None) -> _CliArgs:
    parser = argparse.ArgumentParser(description="Проверка качества docs/scenarios")
    _ = parser.add_argument(
        "--warnings-ok",
        action="store_true",
        help="Не падать на предупреждения taxonomy (orphan tags)",
    )
    ns = parser.parse_args(argv)
    warnings_ok = bool(ns.warnings_ok)
    return _CliArgs(warnings_ok=warnings_ok)


def main() -> int:
    cli_args = _parse_cli_args()
    repo_root = _repo_root()
    scenarios_root = repo_root / "docs" / "scenarios"
    if not scenarios_root.is_dir():
        print(f"Нет каталога {scenarios_root}", file=sys.stderr)
        return 1

    errors: list[str] = []
    warnings: list[str] = []

    errors.extend(check_readme_quality(scenarios_root))
    errors.extend(_check_scenario_marker_en_fields(repo_root / _UI_E2E_ROOT))
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

    if warnings and not cli_args.warnings_ok:
        print(
            (
                f"FAIL: {len(warnings)} предупреждений taxonomy (orphan tags). "
                "Исправьте taxonomy или добавьте --warnings-ok."
            ),
            file=sys.stderr,
        )
        return 1

    print("check_scenario_docs_quality: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
