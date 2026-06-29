"""
Перед сборкой Zensical: деревья build/documentation-ru и build/documentation-en.
Исходники сценариев: docs/scenarios/<service>/<tag>/<slug>/README.md.
В сборке тег — только группировка на hub-страницах; URL: …/scenarios/<service>/<slug>/.
Навигация и learning paths — docs/scenarios/taxonomy.yaml.
"""

from __future__ import annotations

import html
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from scenario_taxonomy import (
    ScenarioTaxonomy,
    load_scenario_taxonomy,
    service_label,
    tag_label,
)

SCENARIOS_ROOT = "scenarios"
ROOT_MARKDOWN_PAGES = ("quickstart.md",)
CURATED_README_MIN_BODY = 80

RU_BUILD = Path("build/documentation-ru")
EN_BUILD = Path("build/documentation-en")

_CRM_BRAND_RE = re.compile(r"(?<![A-Za-z0-9])CRM(?![A-Za-z0-9])")
_CRM_BRAND_TOKEN_RE = re.compile(r"(?<!Amo)CRM")


@dataclass(frozen=True)
class ScenarioEntry:
    src_dir: Path
    service: str
    tag: str
    slug: str


def _brand_display_text(value: str) -> str:
    return _CRM_BRAND_RE.sub("NetWorkle", value)


def _brand_openapi_json(value):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            out[_CRM_BRAND_TOKEN_RE.sub("NetWorkle", key)] = _brand_openapi_json(item)
        return out
    if isinstance(value, list):
        return [_brand_openapi_json(item) for item in value]
    if isinstance(value, str):
        return _CRM_BRAND_TOKEN_RE.sub("NetWorkle", value)
    return value


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


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


def _dest_parts_for_scenario(service: str, slug_name: str) -> tuple[str, ...]:
    return (service, slug_name)


def _collect_scenario_entries(scenarios_root: Path) -> dict[tuple[str, ...], ScenarioEntry]:
    out: dict[tuple[str, ...], ScenarioEntry] = {}
    for service_dir in sorted(p for p in scenarios_root.iterdir() if p.is_dir() and not p.name.startswith(".")):
        service = service_dir.name
        if service == "taxonomy.yaml":
            continue
        for tag_dir in sorted(p for p in service_dir.iterdir() if p.is_dir() and not p.name.startswith(".")):
            tag = tag_dir.name
            for slug_dir in sorted(p for p in tag_dir.iterdir() if p.is_dir() and not p.name.startswith(".")):
                readme = slug_dir / "README.md"
                if not readme.is_file():
                    continue
                slug_name = slug_dir.name
                parts = _dest_parts_for_scenario(service, slug_name)
                if parts in out:
                    raise ValueError(
                        f"Коллизия пути сценариев в сборке: {Path(*parts)!s} — "
                        f"{out[parts].src_dir} и {slug_dir}"
                    )
                out[parts] = ScenarioEntry(
                    src_dir=slug_dir,
                    service=service,
                    tag=tag,
                    slug=slug_name,
                )
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


def _service_intro_from_readme(scenarios_src: Path, service: str, fallback: str) -> str:
    readme = scenarios_src / service / "README.md"
    if not readme.is_file():
        return fallback
    _, body = _readme_body_after_h1(readme.read_text(encoding="utf-8"), service)
    plain = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", body)
    plain = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", plain)
    plain = re.sub(r"\s+", " ", plain).strip()
    if len(plain) >= CURATED_README_MIN_BODY:
        return plain
    return fallback


def _write_grouped_hub_index(
    out: Path,
    *,
    title: str,
    intro: str,
    sections: list[tuple[str, list[tuple[str, str]]]],
    hero_image: str | None = None,
    hero_alt: str | None = None,
) -> None:
    title_json = json.dumps(title, ensure_ascii=False)
    lines = [
        "---",
        f"title: {title_json}",
        "---",
        "",
        intro,
        "",
    ]
    if hero_image is not None:
        alt = hero_alt or title
        lines.extend([f"![{alt}]({hero_image})", ""])
    for section_title, links in sections:
        if not links:
            continue
        lines.extend([f"## {section_title}", "", '<div class="docs-link-grid">'])
        for label, href in links:
            label_html = html.escape(label)
            href_html = html.escape(href, quote=True)
            lines.append(
                f'  <a class="docs-link-card" href="{href_html}">'
                f"<span>{label_html}</span>"
                "</a>"
            )
        lines.extend(["</div>", ""])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")


def _grouped_sections_for_service(
    taxonomy: ScenarioTaxonomy,
    service: str,
    entries: list[ScenarioEntry],
    scenarios_dst: Path,
    *,
    language: str,
) -> list[tuple[str, list[tuple[str, str]]]]:
    spec = taxonomy.services.get(service)
    if spec is None:
        links = []
        for entry in sorted(entries, key=lambda e: e.slug):
            idx = scenarios_dst / service / entry.slug / "index.md"
            if idx.is_file():
                links.append((_title_from_index_md(idx), f"{entry.slug}/"))
        if not links:
            return []
        heading = "Pages" if language == "en" else "Инструкции"
        return [(heading, links)]

    by_tag: dict[str, list[ScenarioEntry]] = {}
    for entry in entries:
        by_tag.setdefault(entry.tag, []).append(entry)

    ordered_tags = sorted(
        spec.tags.keys(),
        key=lambda tag_key: (spec.tags[tag_key].order, tag_key),
    )

    sections: list[tuple[str, list[tuple[str, str]]]] = []
    featured = spec.featured_slug
    if featured is not None:
        featured_idx = scenarios_dst / service / featured / "index.md"
        if featured_idx.is_file():
            featured_heading = "Start here" if language == "en" else "С чего начать"
            sections.append(
                (
                    featured_heading,
                    [(_title_from_index_md(featured_idx), f"{featured}/")],
                )
            )

    for tag_key in ordered_tags:
        tag_entries = by_tag.get(tag_key, [])
        if not tag_entries:
            continue
        links: list[tuple[str, str]] = []
        for entry in sorted(tag_entries, key=lambda e: e.slug):
            if featured is not None and entry.slug == featured:
                continue
            idx = scenarios_dst / service / entry.slug / "index.md"
            if not idx.is_file():
                continue
            links.append((_title_from_index_md(idx), f"{entry.slug}/"))
        if not links:
            continue
        section_title = tag_label(taxonomy, service, tag_key, language=language)
        sections.append((section_title, links))

    return sections


def _write_scenario_hub_indices(
    taxonomy: ScenarioTaxonomy,
    scenarios_src: Path,
    scenarios_dst: Path,
    entries: dict[tuple[str, ...], ScenarioEntry],
    *,
    language: str,
) -> None:
    if not scenarios_dst.is_dir():
        return

    by_service: dict[str, list[ScenarioEntry]] = {}
    for entry in entries.values():
        by_service.setdefault(entry.service, []).append(entry)

    for service in taxonomy.service_order:
        service_entries = by_service.get(service, [])
        if not service_entries:
            continue
        svc_dir = scenarios_dst / service
        if not svc_dir.is_dir():
            continue
        title = service_label(taxonomy, service, language=language)
        spec = taxonomy.services[service]
        fallback_intro = spec.intro_en if language == "en" else spec.intro_ru
        intro = _service_intro_from_readme(scenarios_src, service, fallback_intro)
        sections = _grouped_sections_for_service(
            taxonomy,
            service,
            service_entries,
            scenarios_dst,
            language=language,
        )
        if not sections:
            continue
        hero_image = "screenshots/001.png" if (svc_dir / "screenshots" / "001.png").is_file() else None
        _write_grouped_hub_index(
            svc_dir / "index.md",
            title=title,
            intro=intro,
            sections=sections,
            hero_image=hero_image,
            hero_alt=f"{title}: service home",
        )

    root_links: list[tuple[str, str]] = []
    for service in taxonomy.service_order:
        idx = scenarios_dst / service / "index.md"
        if idx.is_file():
            root_links.append((service_label(taxonomy, service, language=language), f"{service}/"))

    if not root_links:
        return

    root_title = "Instructions" if language == "en" else "Инструкции"
    root_intro = (
        "Step-by-step UI instructions with screenshots from E2E tests."
        if language == "en"
        else "Проверенные пользовательские инструкции с шагами и скриншотами интерфейса."
    )
    _write_grouped_hub_index(
        scenarios_dst / "index.md",
        title=root_title,
        intro=root_intro,
        sections=[("Services" if language == "en" else "Сервисы", root_links)],
    )


def _write_scenarios_pages_file(taxonomy: ScenarioTaxonomy, scenarios_dst: Path) -> None:
    nav_lines = ["nav:"]
    for service in taxonomy.service_order:
        idx = scenarios_dst / service / "index.md"
        if idx.is_file():
            nav_lines.append(f"  - {service}/index.md")
    if len(nav_lines) <= 1:
        return
    (scenarios_dst / ".pages").write_text("\n".join(nav_lines) + "\n", encoding="utf-8")


def _populate_scenario_index_tree(
    taxonomy: ScenarioTaxonomy,
    scenarios_src: Path,
    scenarios_dst: Path,
    *,
    language: str,
) -> None:
    scenarios_dst.mkdir(parents=True, exist_ok=True)
    entries = _collect_scenario_entries(scenarios_src)
    _copy_service_screenshots(scenarios_src, scenarios_dst)
    for parts in sorted(entries, key=lambda t: (len(t), t)):
        entry = entries[parts]
        dst_dir = scenarios_dst.joinpath(*parts)
        dst_dir.mkdir(parents=True, exist_ok=True)
        readme = entry.src_dir / "README.md"
        if language == "en":
            en_readme = entry.src_dir / "README.en.md"
            if en_readme.is_file():
                readme = en_readme
        _write_index_md_from_readme(readme, dst_dir / "index.md")
        _copy_screenshots(entry.src_dir, dst_dir)
    _write_scenario_hub_indices(taxonomy, scenarios_src, scenarios_dst, entries, language=language)
    _write_scenarios_pages_file(taxonomy, scenarios_dst)


def _write_start_here_page(out: Path, taxonomy: ScenarioTaxonomy, *, language: str) -> None:
    if language == "en":
        title = "Start here"
        page_intro = (
            "Pick a learning path below. Each path links to existing step-by-step instructions "
            "with screenshots — no duplicate content on this page."
        )
        paths_heading = "Learning paths"
    else:
        title = "Начни отсюда"
        page_intro = (
            "Выберите маршрут ниже. Каждый маршрут ведёт к готовым пошаговым инструкциям "
            "со скриншотами — на этой странице нет дублирования контента."
        )
        paths_heading = "Маршруты обучения"

    sections: list[tuple[str, list[tuple[str, str]]]] = []
    for path in taxonomy.learning_paths:
        path_label = path.label_en if language == "en" else path.label_ru
        path_intro = path.intro_en if language == "en" else path.intro_ru
        links: list[tuple[str, str]] = []
        for step in path.steps:
            step_label = step.label_en if language == "en" else step.label_ru
            links.append((step_label, step.href))
        section_body = f"{path_intro}\n\n"
        sections.append((f"{path_label}\n\n{section_body.strip()}", links))

    title_json = json.dumps(title, ensure_ascii=False)
    lines = [
        "---",
        f"title: {title_json}",
        "---",
        "",
        page_intro,
        "",
        f"## {paths_heading}",
        "",
    ]
    for path in taxonomy.learning_paths:
        path_label = path.label_en if language == "en" else path.label_ru
        path_intro = path.intro_en if language == "en" else path.intro_ru
        lines.extend([f"### {path_label}", "", path_intro, "", '<div class="docs-link-grid">'])
        for step in path.steps:
            step_label = step.label_en if language == "en" else step.label_ru
            label_html = html.escape(step_label)
            href_html = html.escape(step.href, quote=True)
            lines.append(
                f'  <a class="docs-link-card" href="{href_html}">'
                f"<span>{label_html}</span>"
                "</a>"
            )
        lines.extend(["</div>", ""])

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")


def _copy_optional_subdir(src_root: Path, name: str, dst_root: Path) -> None:
    src = src_root / name
    if src.is_dir():
        shutil.copytree(src, dst_root / name, dirs_exist_ok=False)


def _copy_openapi_subdir(src_root: Path, dst_root: Path) -> None:
    src = src_root / "openapi"
    if not src.is_dir():
        return
    dst = dst_root / "openapi"
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=False)
            continue
        if item.suffix == ".json":
            try:
                payload = json.loads(item.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                shutil.copy2(item, target)
                continue
            target.write_text(
                json.dumps(_brand_openapi_json(payload), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        else:
            shutil.copy2(item, target)


def _copy_root_markdown_pages(src_root: Path, dst_root: Path) -> None:
    for page in ROOT_MARKDOWN_PAGES:
        src = src_root / page
        if src.is_file():
            shutil.copy2(src, dst_root / page)


def _remove_legacy_en_scenarios_mirror(docs_dir: Path) -> None:
    legacy = docs_dir / "en" / SCENARIOS_ROOT
    if legacy.is_dir():
        shutil.rmtree(legacy)


def _prepare_ru_build_tree(docs_dir: Path, ru_dir: Path, taxonomy: ScenarioTaxonomy) -> None:
    if ru_dir.exists():
        shutil.rmtree(ru_dir)
    ru_dir.mkdir(parents=True)

    index_src = docs_dir / "index.md"
    if not index_src.is_file():
        raise FileNotFoundError(f"Нет корневой страницы документации: {index_src}")
    shutil.copy2(index_src, ru_dir / "index.md")
    _copy_root_markdown_pages(docs_dir, ru_dir)
    _write_start_here_page(ru_dir / "start-here.md", taxonomy, language="ru")

    scenarios_src = docs_dir / SCENARIOS_ROOT
    scenarios_dst = ru_dir / SCENARIOS_ROOT
    if scenarios_src.is_dir():
        _populate_scenario_index_tree(taxonomy, scenarios_src, scenarios_dst, language="ru")

    _copy_openapi_subdir(docs_dir, ru_dir)
    _copy_optional_subdir(docs_dir, "assets", ru_dir)


def _prepare_en_build_tree(docs_dir: Path, en_dir: Path, taxonomy: ScenarioTaxonomy) -> None:
    if en_dir.exists():
        shutil.rmtree(en_dir)
    en_dir.mkdir(parents=True)

    en_src = docs_dir / "en"
    en_index = en_src / "index.md"
    if not en_index.is_file():
        raise FileNotFoundError(f"Нет английской корневой страницы: {en_index}")
    shutil.copy2(en_index, en_dir / "index.md")
    _copy_root_markdown_pages(en_src, en_dir)
    _write_start_here_page(en_dir / "start-here.md", taxonomy, language="en")

    _copy_openapi_subdir(docs_dir, en_dir)
    _copy_optional_subdir(docs_dir, "assets", en_dir)

    scenarios_src = docs_dir / SCENARIOS_ROOT
    scenarios_dst = en_dir / SCENARIOS_ROOT
    if scenarios_src.is_dir():
        _populate_scenario_index_tree(taxonomy, scenarios_src, scenarios_dst, language="en")


def _copy_screenshots(src_slug_dir: Path, dst_slug_dir: Path) -> None:
    shots = src_slug_dir / "screenshots"
    if not shots.is_dir():
        return
    dst_shots = dst_slug_dir / "screenshots"
    if dst_shots.exists():
        shutil.rmtree(dst_shots)
    shutil.copytree(shots, dst_shots)


def _copy_service_screenshots(scenarios_src: Path, scenarios_dst: Path) -> None:
    for service_dir in sorted(p for p in scenarios_src.iterdir() if p.is_dir() and not p.name.startswith(".")):
        shots = service_dir / "screenshots"
        if not shots.is_dir():
            continue
        dst_service_dir = scenarios_dst / service_dir.name
        dst_service_dir.mkdir(parents=True, exist_ok=True)
        dst_shots = dst_service_dir / "screenshots"
        if dst_shots.exists():
            shutil.rmtree(dst_shots)
        shutil.copytree(shots, dst_shots)


def _generate_api_docs(ru_dir: Path, en_dir: Path) -> None:
    import sys
    from pathlib import Path as PathLib

    current_dir = PathLib(__file__).resolve().parent
    if str(current_dir) not in sys.path:
        sys.path.insert(0, str(current_dir))

    from openapi_to_markdown import main as generate_markdown

    logger = __import__("logging").getLogger(__name__)
    logger.info("Генерация документации API из OpenAPI схем...")

    try:
        generate_markdown()
        logger.info("Документация API сгенерирована")
    except Exception as e:
        logger.warning(f"Не удалось сгенерировать документацию API: {e}")


def _markdown_without_frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4 :].lstrip()
    return text


def _title_from_markdown(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            fm = text[3:end]
            for line in fm.splitlines():
                stripped = line.strip()
                if stripped.startswith("title:"):
                    raw = stripped.split(":", 1)[1].strip()
                    try:
                        return str(json.loads(raw))[:200]
                    except json.JSONDecodeError:
                        return raw.strip("'\"")[:200]

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()[:200]
    return path.parent.name.replace("-", " ").title()


def _plain_text_excerpt(markdown: str, limit: int = 220) -> str:
    text = _markdown_without_frontmatter(markdown)
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"^[#>*\-\s`]+", "", text, flags=re.M)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _page_url_for_markdown(path: Path, docs_root: Path, base_url: str) -> str:
    rel = path.relative_to(docs_root)
    if rel.name == "index.md":
        url_path = rel.parent.as_posix()
    else:
        url_path = rel.with_suffix("").as_posix()
    if not url_path or url_path == ".":
        return base_url.rstrip("/") + "/"
    return base_url.rstrip("/") + "/" + url_path.rstrip("/") + "/"


def _iter_llms_pages(docs_root: Path) -> list[Path]:
    pages = []
    for path in sorted(docs_root.rglob("*.md")):
        rel_parts = path.relative_to(docs_root).parts
        if any(part.startswith(".") for part in rel_parts):
            continue
        pages.append(path)
    return pages


def _generate_llms_files(docs_root: Path, language: str, base_url: str) -> None:
    if not docs_root.is_dir():
        return

    title = "Humanitec Documentation" if language == "en" else "Документация Humanitec"
    description = (
        "Reference documentation for the Humanitec platform: quickstart, start here, API, and UI instructions."
        if language == "en"
        else "Справочная документация платформы Humanitec: быстрый старт, маршруты обучения, API и UI-инструкции."
    )
    pages = _iter_llms_pages(docs_root)

    llms_lines = [
        f"# {title}",
        "",
        f"> {description}",
        "",
        "## Pages",
        "",
    ]
    full_lines = [f"# {title}", "", description, ""]

    for path in pages:
        markdown = path.read_text(encoding="utf-8")
        page_title = _title_from_markdown(path)
        url = _page_url_for_markdown(path, docs_root, base_url)
        excerpt = _plain_text_excerpt(markdown)
        if excerpt:
            llms_lines.append(f"- [{page_title}]({url}): {excerpt}")
        else:
            llms_lines.append(f"- [{page_title}]({url})")

        full_lines.extend(
            [
                f"## {page_title}",
                "",
                f"Source: {url}",
                "",
                _markdown_without_frontmatter(markdown).strip(),
                "",
            ]
        )

    (docs_root / "llms.txt").write_text("\n".join(llms_lines).rstrip() + "\n", encoding="utf-8")
    (docs_root / "llms-full.txt").write_text("\n".join(full_lines).rstrip() + "\n", encoding="utf-8")


def main() -> None:
    root = _repo_root()
    docs_dir = root / "docs"
    if not docs_dir.is_dir():
        raise FileNotFoundError(f"Нет каталога документации: {docs_dir}")

    _remove_legacy_en_scenarios_mirror(docs_dir)
    taxonomy = load_scenario_taxonomy(root)

    ru_path = root / RU_BUILD
    en_path = root / EN_BUILD
    _prepare_ru_build_tree(docs_dir, ru_path, taxonomy)
    _prepare_en_build_tree(docs_dir, en_path, taxonomy)

    _generate_api_docs(ru_path, en_path)
    _generate_llms_files(ru_path, "ru", "https://humanitec.ru/documentation/")
    _generate_llms_files(en_path, "en", "https://humanitec.ru/documentation/en/")


if __name__ == "__main__":
    main()
