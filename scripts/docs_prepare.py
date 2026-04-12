"""
Перед сборкой Fumadocs: заглушки README для docs/scenarios, index.mdx из README.md
и манифест путей для Next.js generateStaticParams (без импорта collections/server в page).
"""

from __future__ import annotations

import json
from pathlib import Path

SCENARIOS_ROOT = "scenarios"

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


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


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


def _service_label(name: str) -> str:
    return _SERVICE_NAV_LABEL.get(name, name.replace("_", " ").title())


def _tag_label(name: str) -> str:
    return _TAG_NAV_LABEL.get(name, name.replace("_", " ").title())


def _tag_has_scenario_slugs(tag_dir: Path) -> bool:
    for slug_dir in tag_dir.iterdir():
        if slug_dir.is_dir() and (slug_dir / "README.md").is_file():
            return True
    return False


def _service_has_scenario_slugs(service_dir: Path) -> bool:
    for tag_dir in service_dir.iterdir():
        if not tag_dir.is_dir():
            continue
        if _tag_has_scenario_slugs(tag_dir):
            return True
    return False


def _ensure_scenario_readme_stubs(docs_dir: Path) -> None:
    root = docs_dir / SCENARIOS_ROOT
    if not root.is_dir():
        return

    for service_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        if service_dir.name.startswith("."):
            continue
        service = service_dir.name
        svc_label = _service_label(service)
        svc_readme = service_dir / "README.md"
        if not svc_readme.is_file() and _service_has_scenario_slugs(service_dir):
            svc_readme.write_text(
                f"# Сценарии {svc_label}\n\n"
                f"Пошаговые инструкции по интерфейсу продукта {svc_label}, сгруппированные по темам ниже. "
                f"Этот файл создан автоматически при подготовке документации (`make doc`); при необходимости замените текст.\n",
                encoding="utf-8",
            )

        for tag_dir in sorted(p for p in service_dir.iterdir() if p.is_dir()):
            if tag_dir.name.startswith("."):
                continue
            tag = tag_dir.name
            tag_readme = tag_dir / "README.md"
            if tag_readme.is_file():
                continue
            if not _tag_has_scenario_slugs(tag_dir):
                continue
            tag_human = _tag_label(tag)
            tag_readme.write_text(
                f"# {tag_human} ({svc_label})\n\n"
                f"Инструкции по теме «{tag_human}». "
                f"Файл создан автоматически при подготовке документации (`make doc`); отредактируйте при необходимости.\n",
                encoding="utf-8",
            )


def _readme_body_after_h1(text: str, fallback_title: str) -> tuple[str, str]:
    lines = text.splitlines()
    title = ""
    body_start = 0
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("#"):
            title = s.lstrip("#").strip()
            body_start = i + 1
            break
    if not title:
        return fallback_title.replace("_", " "), text.strip()
    body = "\n".join(lines[body_start:]).lstrip("\n")
    return title[:200], body


def _write_index_mdx_from_readme(readme: Path) -> None:
    raw = readme.read_text(encoding="utf-8")
    if raw.strip().startswith("---"):
        raise ValueError(
            f"README с YAML-frontmatter не поддерживается для автогенерации index.mdx: {readme}"
        )
    title, body = _readme_body_after_h1(raw, readme.parent.name)
    title_json = json.dumps(title, ensure_ascii=False)
    out = readme.parent / "index.mdx"
    out.write_text(f"---\ntitle: {title_json}\n---\n\n{body}", encoding="utf-8")


def _sync_scenario_index_mdx(scenarios_root: Path) -> None:
    if not scenarios_root.is_dir():
        return
    for readme in scenarios_root.rglob("README.md"):
        if ".git" in readme.parts:
            continue
        _write_index_mdx_from_readme(readme)


def _write_doc_path_manifest(docs_dir: Path, repo_root: Path) -> None:
    slugs: list[list[str]] = []
    for index in sorted(docs_dir.rglob("index.mdx")):
        rel_parent = index.parent.relative_to(docs_dir)
        if rel_parent == Path("."):
            continue
        slugs.append(list(rel_parent.parts))

    out_dir = repo_root / "apps" / "documentation" / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = out_dir / "doc-paths.json"
    manifest.write_text(
        json.dumps({"slugs": slugs}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    root = _repo_root()
    docs_dir = root / "docs"
    if not docs_dir.is_dir():
        raise FileNotFoundError(f"Нет каталога документации: {docs_dir}")
    _ensure_scenario_readme_stubs(docs_dir)
    _sync_scenario_index_mdx(docs_dir / SCENARIOS_ROOT)
    _write_doc_path_manifest(docs_dir, root)


if __name__ == "__main__":
    main()
