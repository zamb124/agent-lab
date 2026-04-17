"""
Перед сборкой Zensical: заглушки README для docs/scenarios, отдельные деревья
build/documentation-ru и build/documentation-en (без index.md в репозитории сценариев).
В сборке тег general не даёт отдельного уровня: …/service/general/slug → …/service/slug.
"""

from __future__ import annotations

import json
import shutil
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

RU_BUILD = Path("build/documentation-ru")
EN_BUILD = Path("build/documentation-en")

DEFAULT_SCENARIO_TAG = "general"


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


def _write_index_md_from_readme(readme: Path, out: Path) -> None:
    raw = readme.read_text(encoding="utf-8")
    if raw.strip().startswith("---"):
        raise ValueError(
            f"README с YAML-frontmatter не поддерживается для автогенерации index.md: {readme}"
        )
    title, body = _readme_body_after_h1(raw, readme.parent.name)
    title_json = json.dumps(title, ensure_ascii=False)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(f"---\ntitle: {title_json}\n---\n\n{body}", encoding="utf-8")


def _dest_parts_for_scenario(service: str, tag: str, slug_name: str) -> tuple[str, ...]:
    if tag == DEFAULT_SCENARIO_TAG:
        return (service, slug_name)
    return (service, tag, slug_name)


def _collect_scenario_slug_readmes(scenarios_root: Path) -> dict[tuple[str, ...], Path]:
    out: dict[tuple[str, ...], Path] = {}
    for service_dir in sorted(p for p in scenarios_root.iterdir() if p.is_dir() and not p.name.startswith(".")):
        service = service_dir.name
        for tag_dir in sorted(p for p in service_dir.iterdir() if p.is_dir() and not p.name.startswith(".")):
            tag = tag_dir.name
            for slug_dir in sorted(p for p in tag_dir.iterdir() if p.is_dir() and not p.name.startswith(".")):
                readme = slug_dir / "README.md"
                if not readme.is_file():
                    continue
                slug_name = slug_dir.name
                if tag == DEFAULT_SCENARIO_TAG and slug_name != DEFAULT_SCENARIO_TAG:
                    sibling = scenarios_root / service / slug_name
                    if sibling.is_dir():
                        raise ValueError(
                            f"Сценарий {service}/{DEFAULT_SCENARIO_TAG}/{slug_name}: каталог "
                            f"«{service}/{slug_name}» уже существует как тег; переименуйте doc_slug."
                        )
                parts = _dest_parts_for_scenario(service, tag, slug_name)
                if parts in out:
                    raise ValueError(
                        f"Коллизия пути сценариев в сборке: {Path(*parts)!s} — {out[parts]} и {slug_dir}"
                    )
                out[parts] = slug_dir
    return out


def _title_from_index_md(index_path: Path) -> str:
    text = index_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return index_path.parent.name
    end = text.find("\n---", 3)
    if end == -1:
        return index_path.parent.name
    fm = text[3:end]
    for line in fm.splitlines():
        stripped = line.strip()
        if stripped.startswith("title:"):
            raw = stripped.split(":", 1)[1].strip()
            try:
                return str(json.loads(raw))[:200]
            except json.JSONDecodeError:
                return raw.strip("'\"")[:200]
    return index_path.parent.name


def _is_leaf_scenario_build_dir(d: Path) -> bool:
    if not (d / "index.md").is_file():
        return False
    for sub in d.iterdir():
        if not sub.is_dir() or sub.name.startswith("."):
            continue
        if sub.name == "screenshots":
            continue
        if (sub / "index.md").is_file():
            return False
    return True


def _is_tag_container_build_dir(d: Path) -> bool:
    if not d.is_dir() or (d / "index.md").is_file():
        return False
    for sub in d.iterdir():
        if not sub.is_dir() or sub.name.startswith("."):
            continue
        if (sub / "index.md").is_file():
            return True
    return False


def _write_hub_index(out: Path, title: str, intro: str, links: list[tuple[str, str]]) -> None:
    title_json = json.dumps(title, ensure_ascii=False)
    lines = ["---", f"title: {title_json}", "---", "", intro, "", "## Сценарии", ""]
    for label, href in sorted(links, key=lambda x: x[0].lower()):
        lines.append(f"- [{label}]({href})")
    lines.append("")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")


def _write_ru_scenario_hub_indices(scenarios_dst: Path) -> None:
    if not scenarios_dst.is_dir():
        return
    for svc_dir in sorted(p for p in scenarios_dst.iterdir() if p.is_dir() and not p.name.startswith(".")):
        service = svc_dir.name
        links: list[tuple[str, str]] = []
        for child in sorted((x for x in svc_dir.iterdir() if x.is_dir() and not x.name.startswith(".")), key=lambda p: p.name):
            idx = child / "index.md"
            if _is_leaf_scenario_build_dir(child):
                if not idx.is_file():
                    continue
                links.append((_title_from_index_md(idx), f"{child.name}/"))
            elif _is_tag_container_build_dir(child):
                links.append((_tag_label(child.name), f"{child.name}/"))
        if not links:
            continue
        title = _service_label(service)
        intro = f"Пошаговые сценарии интерфейса {title}."
        _write_hub_index(svc_dir / "index.md", title, intro, links)

    for svc_dir in sorted(p for p in scenarios_dst.iterdir() if p.is_dir() and not p.name.startswith(".")):
        service = svc_dir.name
        svc_label = _service_label(service)
        for tag_dir in sorted(
            (x for x in svc_dir.iterdir() if x.is_dir() and not x.name.startswith(".")),
            key=lambda p: p.name,
        ):
            if not _is_tag_container_build_dir(tag_dir):
                continue
            tag_name = tag_dir.name
            links_t: list[tuple[str, str]] = []
            for slug_child in sorted(
                (x for x in tag_dir.iterdir() if x.is_dir() and not x.name.startswith(".")),
                key=lambda p: p.name,
            ):
                sidx = slug_child / "index.md"
                if not sidx.is_file():
                    continue
                links_t.append((_title_from_index_md(sidx), f"{slug_child.name}/"))
            if not links_t:
                continue
            tag_title = _tag_label(tag_name)
            intro_t = f"Сценарии в группе «{tag_title}» ({svc_label})."
            _write_hub_index(tag_dir / "index.md", tag_title, intro_t, links_t)


def _populate_ru_scenario_index_tree(scenarios_src: Path, scenarios_dst: Path) -> None:
    scenarios_dst.mkdir(parents=True, exist_ok=True)
    mapping = _collect_scenario_slug_readmes(scenarios_src)
    for parts in sorted(mapping, key=lambda t: (len(t), t)):
        src_dir = mapping[parts]
        dst_dir = scenarios_dst.joinpath(*parts)
        dst_dir.mkdir(parents=True, exist_ok=True)
        _write_index_md_from_readme(src_dir / "README.md", dst_dir / "index.md")
        _copy_screenshots(src_dir, dst_dir)
    _write_ru_scenario_hub_indices(scenarios_dst)


def _copy_optional_subdir(src_root: Path, name: str, dst_root: Path) -> None:
    src = src_root / name
    if src.is_dir():
        shutil.copytree(src, dst_root / name, dirs_exist_ok=False)


def _remove_legacy_en_scenarios_mirror(docs_dir: Path) -> None:
    legacy = docs_dir / "en" / SCENARIOS_ROOT
    if legacy.is_dir():
        shutil.rmtree(legacy)


def _prepare_ru_build_tree(docs_dir: Path, ru_dir: Path) -> None:
    if ru_dir.exists():
        shutil.rmtree(ru_dir)
    ru_dir.mkdir(parents=True)

    index_src = docs_dir / "index.md"
    if not index_src.is_file():
        raise FileNotFoundError(f"Нет корневой страницы документации: {index_src}")
    shutil.copy2(index_src, ru_dir / "index.md")

    guides_src = docs_dir / "guides"
    if guides_src.is_dir():
        shutil.copytree(guides_src, ru_dir / "guides", dirs_exist_ok=False)

    scenarios_src = docs_dir / SCENARIOS_ROOT
    scenarios_dst = ru_dir / SCENARIOS_ROOT
    if scenarios_src.is_dir():
        _populate_ru_scenario_index_tree(scenarios_src, scenarios_dst)

    for extra in ("openapi", "assets"):
        _copy_optional_subdir(docs_dir, extra, ru_dir)


def _copy_screenshots(src_slug_dir: Path, dst_slug_dir: Path) -> None:
    shots = src_slug_dir / "screenshots"
    if not shots.is_dir():
        return
    dst_shots = dst_slug_dir / "screenshots"
    if dst_shots.exists():
        shutil.rmtree(dst_shots)
    shutil.copytree(shots, dst_shots)


def _build_en_scenarios_from_readme_en(scenarios_src: Path, en_scenarios_out: Path) -> None:
    if en_scenarios_out.exists():
        shutil.rmtree(en_scenarios_out)
    if not scenarios_src.is_dir():
        return

    found_any = False
    for readme_en in scenarios_src.rglob("README.en.md"):
        if ".git" in readme_en.parts:
            continue
        rel = readme_en.parent.relative_to(scenarios_src)
        parts_src = rel.parts
        if len(parts_src) != 3:
            continue
        service, tag, slug_name = parts_src
        found_any = True
        dest_parts = _dest_parts_for_scenario(service, tag, slug_name)
        out_dir = en_scenarios_out.joinpath(*dest_parts)
        out_dir.mkdir(parents=True, exist_ok=True)
        _write_index_md_from_readme(readme_en, out_dir / "index.md")
        _copy_screenshots(readme_en.parent, out_dir)

    if not found_any:
        return

    missing_parents: set[Path] = set()
    for idx in en_scenarios_out.rglob("index.md"):
        d = idx.parent
        cur = d.parent
        while cur != en_scenarios_out:
            if not (cur / "index.md").is_file():
                missing_parents.add(cur)
            cur = cur.parent

    for d in sorted(missing_parents, key=lambda p: len(p.parts), reverse=True):
        if (d / "index.md").is_file():
            continue
        subdirs = sorted(
            x
            for x in d.iterdir()
            if x.is_dir() and not x.name.startswith(".") and (x / "index.md").is_file()
        )
        if not subdirs:
            continue
        title = d.name.replace("_", " ").replace("-", " ").strip() or d.name
        title_json = json.dumps(title, ensure_ascii=False)
        lines = [
            "---",
            f"title: {title_json}",
            "---",
            "",
            "## Pages",
            "",
        ]
        for sub in subdirs:
            lines.append(f"- [{sub.name}]({sub.name}/)")
        lines.append("")
        (d / "index.md").write_text("\n".join(lines), encoding="utf-8")

    services = sorted(
        x.name
        for x in en_scenarios_out.iterdir()
        if x.is_dir() and not x.name.startswith(".") and any(x.rglob("index.md"))
    )
    if not services:
        return
    lines = [
        "---",
        'title: "E2E scenarios"',
        "---",
        "",
        "Step-by-step UI scenarios with screenshots (tests with `title_en` / `description_en`).",
        "",
        "## Services",
        "",
    ]
    for svc in services:
        lines.append(f"- [{svc}]({svc}/)")
    lines.append("")
    (en_scenarios_out / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _prepare_en_build_tree(docs_dir: Path, en_dir: Path) -> None:
    if en_dir.exists():
        shutil.rmtree(en_dir)
    en_dir.mkdir(parents=True)

    en_src = docs_dir / "en"
    en_index = en_src / "index.md"
    if not en_index.is_file():
        raise FileNotFoundError(f"Нет английской корневой страницы: {en_index}")
    shutil.copy2(en_index, en_dir / "index.md")

    guides_en = en_src / "guides"
    if guides_en.is_dir():
        shutil.copytree(guides_en, en_dir / "guides", dirs_exist_ok=False)

    for extra in ("openapi", "assets"):
        _copy_optional_subdir(docs_dir, extra, en_dir)

    _build_en_scenarios_from_readme_en(docs_dir / SCENARIOS_ROOT, en_dir / SCENARIOS_ROOT)


def _generate_api_docs(ru_dir: Path, en_dir: Path) -> None:
    """Генерирует документацию API из OpenAPI схем."""
    import sys
    from pathlib import Path as PathLib
    
    # Добавляем текущую директорию в sys.path для импорта openapi_to_markdown
    current_dir = PathLib(__file__).resolve().parent
    if str(current_dir) not in sys.path:
        sys.path.insert(0, str(current_dir))
    
    from openapi_to_markdown import main as generate_markdown
    
    logger = __import__("logging").getLogger(__name__)
    logger.info("Генерация документации API из OpenAPI схем...")
    
    try:
        generate_markdown()
        logger.info("✅ Документация API сгенерирована")
    except Exception as e:
        logger.warning(f"⚠️ Не удалось сгенерировать документацию API: {e}")


def main() -> None:
    root = _repo_root()
    docs_dir = root / "docs"
    if not docs_dir.is_dir():
        raise FileNotFoundError(f"Нет каталога документации: {docs_dir}")

    _remove_legacy_en_scenarios_mirror(docs_dir)
    _ensure_scenario_readme_stubs(docs_dir)

    ru_path = root / RU_BUILD
    en_path = root / EN_BUILD
    _prepare_ru_build_tree(docs_dir, ru_path)
    _prepare_en_build_tree(docs_dir, en_path)
    
    # Генерация документации API
    _generate_api_docs(ru_path, en_path)


if __name__ == "__main__":
    main()
