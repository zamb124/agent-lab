"""
Хук MkDocs: навигация «Сценарии (E2E, автогенерация)» по иерархии
docs/scenarios/<сервис>/<тег>/<тест>/README.md (заголовок — первая строка «# …»).
"""

from __future__ import annotations

from pathlib import Path

SCENARIO_NAV_TITLE = "Сценарии (E2E, автогенерация)"
SCENARIOS_ROOT = "scenarios"

# Подписи в сайдбаре (папки — латиница; здесь человекочитаемые заголовки)
_SERVICE_NAV_LABEL: dict[str, str] = {
    "sync": "Sync",
    "flows": "Flows",
    "crm": "CRM",
    "rag": "RAG",
    "frontend": "Frontend",
}

_TAG_NAV_LABEL: dict[str, str] = {
    "general": "Общее",
    "spaces": "Пространства",
}


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


def _service_label(name: str) -> str:
    return _SERVICE_NAV_LABEL.get(name, name.replace("_", " ").title())


def _tag_label(name: str) -> str:
    return _TAG_NAV_LABEL.get(name, name.replace("_", " ").title())


def _build_scenario_nav_entries(docs_dir: Path) -> list:
    root = docs_dir / SCENARIOS_ROOT
    if not root.is_dir():
        return []

    seen_titles: set[str] = set()
    block: list = []

    overview = root / "README.md"
    if overview.is_file():
        rel = overview.relative_to(docs_dir).as_posix()
        t = _unique_nav_title(_title_from_readme(overview), seen_titles)
        block.append({t: rel})

    by_service: dict[str, dict[str, list[dict[str, str]]]] = {}

    for service_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        service = service_dir.name
        for tag_dir in sorted(p for p in service_dir.iterdir() if p.is_dir()):
            tag = tag_dir.name
            for slug_dir in sorted(p for p in tag_dir.iterdir() if p.is_dir()):
                readme = slug_dir / "README.md"
                if not readme.is_file():
                    continue
                try:
                    rel = readme.relative_to(docs_dir).as_posix()
                except ValueError:
                    continue
                raw_title = _title_from_readme(readme)
                title = _unique_nav_title(raw_title, seen_titles)
                by_service.setdefault(service, {}).setdefault(tag, []).append({title: rel})

    for service in sorted(by_service.keys()):
        svc_label = _service_label(service)
        tag_list: list = []
        for tag in sorted(by_service[service].keys()):
            entries = by_service[service][tag]
            if not entries:
                continue
            tag_list.append({_tag_label(tag): entries})
        if tag_list:
            block.append({svc_label: tag_list})

    return block


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
