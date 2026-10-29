"""Перегенерация README.en.md из метаданных @pytest.mark.scenario без E2E-прогона."""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from scripts.docs.scenario_taxonomy import DEFAULT_SCENARIO_TAG, load_scenario_taxonomy

_IMAGE_LINK_RE = re.compile(r"!\[[^\]]*\]\(([^)]+\.png)\)")
_RU_STEP_HEADING_RE = re.compile(r"^##\s+Шаг\s+(\d+)\.\s+(.+)\s*$")


@dataclass(frozen=True)
class ScenarioMeta:
    service: str
    tag: str
    doc_slug: str | None
    test_name: str
    title_en: str
    description_en: str | None


@dataclass(frozen=True)
class ReadmeStep:
    label_ru: str
    image_ref: str | None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _ast_str(node: ast.expr | None) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        value = node.value.strip()
        return value if value else None
    return None


def _step_label_en_map(path: Path) -> dict[str, str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    mapping: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "step":
            continue
        if not isinstance(func.value, ast.Name) or func.value.id != "scenario":
            continue
        ru_label = _ast_str(node.args[0]) if node.args else None
        step_kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg is not None}
        label_en = _ast_str(step_kwargs.get("label_en"))
        details_en = _ast_str(step_kwargs.get("details_en"))
        if ru_label is None or label_en is None:
            continue
        mapping[ru_label] = label_en
        if details_en is not None:
            mapping[f"{ru_label}\0details"] = details_en
    return mapping


def _collect_scenarios(tests_root: Path) -> list[tuple[Path, ScenarioMeta]]:
    scenarios: list[tuple[Path, ScenarioMeta]] = []
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
                if service is None:
                    raise ValueError(f"{path}:{node.lineno} scenario без service")
                tag = _ast_str(kwargs.get("tag")) or DEFAULT_SCENARIO_TAG
                doc_slug = _ast_str(kwargs.get("doc_slug"))
                title_en = _ast_str(kwargs.get("title_en"))
                if title_en is None:
                    raise ValueError(f"{path}:{node.lineno} {node.name}: нет title_en")
                description_en = _ast_str(kwargs.get("description_en"))
                scenarios.append(
                    (
                        path,
                        ScenarioMeta(
                            service=service,
                            tag=tag,
                            doc_slug=doc_slug,
                            test_name=node.name,
                            title_en=title_en,
                            description_en=description_en,
                        ),
                    )
                )
    return scenarios


def _slug_dir_for_scenario(scenarios_root: Path, meta: ScenarioMeta) -> Path:
    if meta.doc_slug is not None:
        slug = meta.doc_slug
    else:
        slug = meta.test_name.removeprefix("test_")
    return scenarios_root / meta.service / meta.tag / slug


def _parse_readme_steps(readme: Path) -> list[ReadmeStep]:
    text = readme.read_text(encoding="utf-8")
    lines = text.splitlines()
    steps: list[ReadmeStep] = []
    current_label: str | None = None
    current_image: str | None = None
    for line in lines:
        heading = _RU_STEP_HEADING_RE.match(line.strip())
        if heading is not None:
            if current_label is not None:
                steps.append(ReadmeStep(label_ru=current_label, image_ref=current_image))
            current_label = heading.group(2).strip()
            current_image = None
            continue
        if current_label is not None:
            image_match = _IMAGE_LINK_RE.search(line)
            if image_match is not None:
                current_image = image_match.group(1)
    if current_label is not None:
        steps.append(ReadmeStep(label_ru=current_label, image_ref=current_image))
    return steps


def _write_en_readme(
    out: Path,
    meta: ScenarioMeta,
    steps: list[ReadmeStep],
    label_en_map: dict[str, str],
) -> None:
    lines = [f"# {meta.title_en}", ""]
    if meta.description_en:
        lines.extend([meta.description_en, ""])
    for index, step in enumerate(steps, start=1):
        label_en = label_en_map.get(step.label_ru)
        if label_en is None:
            raise ValueError(f"нет label_en для шага {step.label_ru!r}")
        lines.append(f"## Step {index}. {label_en}")
        lines.append("")
        details_en = label_en_map.get(f"{step.label_ru}\0details")
        if details_en:
            lines.extend([details_en.strip(), ""])
        if step.image_ref:
            lines.append(f"![{label_en}]({step.image_ref})")
            lines.append("")
    _ = out.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    repo_root = _repo_root()
    _ = load_scenario_taxonomy(repo_root)
    scenarios_root = repo_root / "docs" / "scenarios"
    tests_root = repo_root / "tests" / "ui" / "e2e"
    label_maps: dict[Path, dict[str, str]] = {}
    updated = 0
    skipped = 0
    for path, meta in _collect_scenarios(tests_root):
        slug_dir = _slug_dir_for_scenario(scenarios_root, meta)
        readme = slug_dir / "README.md"
        if not readme.is_file():
            print(f"SKIP: нет README.md для {meta.test_name} -> {slug_dir}", file=sys.stderr)
            skipped += 1
            continue
        if path not in label_maps:
            label_maps[path] = _step_label_en_map(path)
        steps = _parse_readme_steps(readme)
        if not steps:
            raise ValueError(f"{slug_dir}: README.md без шагов")
        en_path = slug_dir / "README.en.md"
        _write_en_readme(en_path, meta, steps, label_maps[path])
        updated += 1
    print(f"regenerate_scenario_readme_en: обновлено {updated}, пропущено {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
