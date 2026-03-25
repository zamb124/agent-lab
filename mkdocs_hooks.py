"""
Хук MkDocs: навигация «Сценарии (E2E, автогенерация)» собирается из docs/scenarios/**/README.md
(заголовок — первая строка вида «# …»). Ручное перечисление в mkdocs.yml не нужно.
"""

from __future__ import annotations

from pathlib import Path

SCENARIO_NAV_TITLE = "Сценарии (E2E, автогенерация)"
SCENARIOS_ROOT = "scenarios"


def _docs_dir(config) -> Path:
    raw = config.get("docs_dir") or "docs"
    base = Path(config["config_file_path"]).resolve().parent
    p = Path(raw)
    if not p.is_absolute():
        p = base / p
    return p.resolve()


def _title_from_readme(readme: Path) -> str:
    try:
        text = readme.read_text(encoding="utf-8")
    except OSError:
        return readme.parent.name
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#"):
            title = line.lstrip("#").strip()
            if title:
                return title[:200]
    return readme.parent.name


def _unique_nav_title(title: str, seen: set[str]) -> str:
    base = title
    candidate = title
    n = 2
    key = candidate.lower()
    while key in seen:
        candidate = f"{base} ({n})"
        n += 1
        key = candidate.lower()
    seen.add(key)
    return candidate


def _build_scenario_nav_entries(docs_dir: Path) -> list[dict[str, str]]:
    root = docs_dir / SCENARIOS_ROOT
    if not root.is_dir():
        return []

    readmes: list[Path] = []
    overview = root / "README.md"
    if overview.is_file():
        readmes.append(overview)
    for path in sorted(root.rglob("README.md")):
        if path == overview:
            continue
        readmes.append(path)

    seen_titles: set[str] = set()
    entries: list[dict[str, str]] = []
    for readme in readmes:
        try:
            rel = readme.relative_to(docs_dir).as_posix()
        except ValueError:
            continue
        raw_title = _title_from_readme(readme)
        title = _unique_nav_title(raw_title, seen_titles)
        entries.append({title: rel})
    return entries


def _nav_without_scenario_block(nav: list) -> list:
    out: list = []
    for item in nav:
        if isinstance(item, dict) and SCENARIO_NAV_TITLE in item:
            continue
        out.append(item)
    return out


def on_config(config, **kwargs):
    docs_dir = _docs_dir(config)
    entries = _build_scenario_nav_entries(docs_dir)
    nav = config.get("nav")
    if not isinstance(nav, list):
        return config

    base = _nav_without_scenario_block(nav)
    if not entries:
        config["nav"] = base
        return config

    insert_at = 1 if len(base) >= 1 else 0
    block = {SCENARIO_NAV_TITLE: entries}
    new_nav = list(base[:insert_at]) + [block] + list(base[insert_at:])
    config["nav"] = new_nav
    return config
