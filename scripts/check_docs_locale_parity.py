"""Check that RU and EN documentation expose the same page and asset routes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

IGNORED_MARKDOWN_FILES = {"llms.txt", "llms-full.txt"}


def _rel_files(root: Path, *, suffixes: tuple[str, ...]) -> set[str]:
    if not root.is_dir():
        return set()
    out: set[str] = set()
    for path in root.rglob("*"):
        if not path.is_file() or path.name in IGNORED_MARKDOWN_FILES:
            continue
        if suffixes and path.suffix not in suffixes:
            continue
        out.add(path.relative_to(root).as_posix())
    return out


def _rel_scenario_screenshots(root: Path) -> set[str]:
    scenarios = root / "scenarios"
    if not scenarios.is_dir():
        return set()
    out: set[str] = set()
    for path in scenarios.rglob("*"):
        if not path.is_file() or "screenshots" not in path.parts:
            continue
        out.add(path.relative_to(scenarios).as_posix())
    return out


def _rel_site_html(root: Path, *, nested_locale: str | None = None) -> set[str]:
    if nested_locale:
        root = root / nested_locale
    if not root.is_dir():
        return set()

    out: set[str] = set()
    for path in root.rglob("*.html"):
        rel = path.relative_to(root)
        if not nested_locale and rel.parts and rel.parts[0] == "en":
            continue
        out.add(rel.as_posix())
    return out


def _compare_sets(label: str, ru: set[str], en: set[str]) -> list[str]:
    errors: list[str] = []
    only_ru = sorted(ru - en)
    only_en = sorted(en - ru)
    if only_ru:
        preview = "\n  ".join(only_ru[:30])
        errors.append(f"{label}: есть только в RU ({len(only_ru)}):\n  {preview}")
    if only_en:
        preview = "\n  ".join(only_en[:30])
        errors.append(f"{label}: есть только в EN ({len(only_en)}):\n  {preview}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ru", type=Path, default=Path("build/documentation-ru"))
    parser.add_argument("--en", type=Path, default=Path("build/documentation-en"))
    parser.add_argument("--site", type=Path, default=None)
    args = parser.parse_args()

    errors: list[str] = []
    errors.extend(
        _compare_sets(
            "Markdown pages",
            _rel_files(args.ru, suffixes=(".md",)),
            _rel_files(args.en, suffixes=(".md",)),
        )
    )
    errors.extend(
        _compare_sets(
            "OpenAPI schemas",
            _rel_files(args.ru / "openapi", suffixes=(".json",)),
            _rel_files(args.en / "openapi", suffixes=(".json",)),
        )
    )
    errors.extend(
        _compare_sets(
            "Scenario screenshots",
            _rel_scenario_screenshots(args.ru),
            _rel_scenario_screenshots(args.en),
        )
    )

    if args.site is not None:
        errors.extend(
            _compare_sets(
                "Built HTML pages",
                _rel_site_html(args.site),
                _rel_site_html(args.site, nested_locale="en"),
            )
        )

    if errors:
        print("docs locale parity: FAILED", file=sys.stderr)
        print("\n\n".join(errors), file=sys.stderr)
        return 1

    print("docs locale parity: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
