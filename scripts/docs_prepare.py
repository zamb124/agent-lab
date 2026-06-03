"""
Перед сборкой Zensical: заглушки README для docs/scenarios, отдельные деревья
build/documentation-ru и build/documentation-en (без index.md в репозитории сценариев).
В сборке теги остаются только внутренней группировкой исходников:
…/service/<tag>/slug → …/service/slug, чтобы навигация документации была без лишних уровней.
"""

from __future__ import annotations

import html
import json
import re
import shutil
from pathlib import Path

SCENARIOS_ROOT = "scenarios"
ROOT_MARKDOWN_PAGES = ("quickstart.md",)

_SERVICE_NAV_LABEL: dict[str, str] = {
    "sync": "Sync",
    "flows": "Flows",
    "platform": "Основные инструкции",
    "crm": "NetWorkle",
    "rag": "RAG",
    "frontend": "Frontend",
}

_SERVICE_NAV_LABEL_EN: dict[str, str] = {
    "sync": "Sync",
    "flows": "Flows",
    "platform": "Platform Basics",
    "crm": "NetWorkle",
    "rag": "RAG",
    "frontend": "Frontend",
}

_SERVICE_SCENARIO_INTRO_RU: dict[str, str] = {
    "platform": "Базовые инструкции для нового пользователя: вход, Dashboard, список сервисов и меню аккаунта.",
    "flows": "Пошаговые инструкции по Flows: главная сервиса, запуск агента в чате, создание и редактирование flow, операции published flow и Evaluation Lab.",
}

_SERVICE_SCENARIO_INTRO_EN: dict[str, str] = {
    "platform": "Basic instructions for a new user: entry, Dashboard, service list, and account menu.",
    "flows": "Step-by-step Flows instructions: service home, agent chat, creating and editing flows, published-flow operations, and Evaluation Lab.",
}

_TAG_NAV_LABEL: dict[str, str] = {
    "general": "Общее",
    "spaces": "Пространства",
}

RU_BUILD = Path("build/documentation-ru")
EN_BUILD = Path("build/documentation-en")

DEFAULT_SCENARIO_TAG = "general"
_CRM_BRAND_RE = re.compile(r"(?<![A-Za-z0-9])CRM(?![A-Za-z0-9])")
_CRM_BRAND_TOKEN_RE = re.compile(r"(?<!Amo)CRM")


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


def _service_label_en(name: str) -> str:
    return _SERVICE_NAV_LABEL_EN.get(name, name.replace("_", " ").replace("-", " ").title())


def _service_intro_ru(service: str, title: str) -> str:
    return _SERVICE_SCENARIO_INTRO_RU.get(service, f"Пошаговые инструкции интерфейса {title}.")


def _service_intro_en(service: str) -> str:
    return _SERVICE_SCENARIO_INTRO_EN.get(service, "Step-by-step UI instructions with screenshots.")


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
                f"# Инструкции {svc_label}\n\n"
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
    _ = tag
    return (service, slug_name)


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


def _write_hub_index(
    out: Path,
    title: str,
    intro: str,
    links: list[tuple[str, str]],
    *,
    heading: str = "Инструкции",
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
    lines.extend([f"## {heading}", "", '<div class="docs-link-grid">'])
    for label, href in sorted(links, key=lambda x: x[0].lower()):
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


def _write_ru_scenarios_root_index(scenarios_dst: Path) -> None:
    if not scenarios_dst.is_dir():
        return

    links: list[tuple[str, str]] = []
    for svc_dir in sorted(p for p in scenarios_dst.iterdir() if p.is_dir() and not p.name.startswith(".")):
        idx = svc_dir / "index.md"
        if idx.is_file():
            links.append((_service_label(svc_dir.name), f"{svc_dir.name}/"))

    if not links:
        return

    _write_hub_index(
        scenarios_dst / "index.md",
        "Инструкции",
        "Проверенные пользовательские инструкции с шагами и скриншотами интерфейса.",
        links,
    )


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
        intro = _service_intro_ru(service, title)
        hero_image = "screenshots/001.png" if (svc_dir / "screenshots" / "001.png").is_file() else None
        _write_hub_index(
            svc_dir / "index.md",
            title,
            intro,
            links,
            hero_image=hero_image,
            hero_alt=f"{title}: главная страница сервиса",
        )

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
            intro_t = f"Инструкции в группе «{tag_title}» ({svc_label})."
            _write_hub_index(tag_dir / "index.md", tag_title, intro_t, links_t)

    _write_ru_scenarios_root_index(scenarios_dst)


def _populate_ru_scenario_index_tree(scenarios_src: Path, scenarios_dst: Path) -> None:
    scenarios_dst.mkdir(parents=True, exist_ok=True)
    mapping = _collect_scenario_slug_readmes(scenarios_src)
    _copy_service_screenshots(scenarios_src, scenarios_dst)
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


def _prepare_ru_build_tree(docs_dir: Path, ru_dir: Path) -> None:
    if ru_dir.exists():
        shutil.rmtree(ru_dir)
    ru_dir.mkdir(parents=True)

    index_src = docs_dir / "index.md"
    if not index_src.is_file():
        raise FileNotFoundError(f"Нет корневой страницы документации: {index_src}")
    shutil.copy2(index_src, ru_dir / "index.md")
    _copy_root_markdown_pages(docs_dir, ru_dir)

    guides_src = docs_dir / "guides"
    if guides_src.is_dir():
        shutil.copytree(guides_src, ru_dir / "guides", dirs_exist_ok=False)

    scenarios_src = docs_dir / SCENARIOS_ROOT
    scenarios_dst = ru_dir / SCENARIOS_ROOT
    if scenarios_src.is_dir():
        _populate_ru_scenario_index_tree(scenarios_src, scenarios_dst)

    _copy_openapi_subdir(docs_dir, ru_dir)
    _copy_optional_subdir(docs_dir, "assets", ru_dir)


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


def _build_en_scenarios_from_readmes(scenarios_src: Path, en_scenarios_out: Path) -> None:
    if en_scenarios_out.exists():
        shutil.rmtree(en_scenarios_out)
    if not scenarios_src.is_dir():
        return

    mapping = _collect_scenario_slug_readmes(scenarios_src)
    _copy_service_screenshots(scenarios_src, en_scenarios_out)
    for dest_parts, src_dir in sorted(mapping.items(), key=lambda item: item[0]):
        readme = src_dir / "README.en.md"
        if not readme.is_file():
            readme = src_dir / "README.md"
        out_dir = en_scenarios_out.joinpath(*dest_parts)
        out_dir.mkdir(parents=True, exist_ok=True)
        _write_index_md_from_readme(readme, out_dir / "index.md")
        _copy_screenshots(src_dir, out_dir)

    if not mapping:
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
        title = _service_label_en(d.name)
        links = [(_title_from_index_md(sub / "index.md"), f"{sub.name}/") for sub in subdirs]
        hero_image = "screenshots/001.png" if (d / "screenshots" / "001.png").is_file() else None
        _write_hub_index(
            d / "index.md",
            title,
            _service_intro_en(d.name),
            links,
            heading="Pages",
            hero_image=hero_image,
            hero_alt=f"{title}: service home page",
        )

    services = sorted(
        x.name
        for x in en_scenarios_out.iterdir()
        if x.is_dir() and not x.name.startswith(".") and any(x.rglob("index.md"))
    )
    if not services:
        return
    _write_hub_index(
        en_scenarios_out / "index.md",
        "E2E instructions",
        "Step-by-step UI instructions with screenshots generated from the same tests as the Russian documentation.",
        [(_service_label_en(svc), f"{svc}/") for svc in services],
        heading="Services",
    )


def _prepare_en_build_tree(docs_dir: Path, en_dir: Path) -> None:
    if en_dir.exists():
        shutil.rmtree(en_dir)
    en_dir.mkdir(parents=True)

    en_src = docs_dir / "en"
    en_index = en_src / "index.md"
    if not en_index.is_file():
        raise FileNotFoundError(f"Нет английской корневой страницы: {en_index}")
    shutil.copy2(en_index, en_dir / "index.md")
    _copy_root_markdown_pages(en_src, en_dir)

    guides_en = en_src / "guides"
    if guides_en.is_dir():
        shutil.copytree(guides_en, en_dir / "guides", dirs_exist_ok=False)

    _copy_openapi_subdir(docs_dir, en_dir)
    _copy_optional_subdir(docs_dir, "assets", en_dir)

    _build_en_scenarios_from_readmes(docs_dir / SCENARIOS_ROOT, en_dir / SCENARIOS_ROOT)


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
        if any(part.startswith(".") for part in path.relative_to(docs_root).parts):
            continue
        pages.append(path)
    return pages


def _generate_llms_files(docs_root: Path, language: str, base_url: str) -> None:
    if not docs_root.is_dir():
        return

    title = "Humanitec Documentation" if language == "en" else "Документация Humanitec"
    description = (
        "Reference documentation for the Humanitec platform: quickstart, API, guides, and UI instructions."
        if language == "en"
        else "Справочная документация платформы Humanitec: быстрый старт, API, руководства и UI-инструкции."
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
    _ensure_scenario_readme_stubs(docs_dir)

    ru_path = root / RU_BUILD
    en_path = root / EN_BUILD
    _prepare_ru_build_tree(docs_dir, ru_path)
    _prepare_en_build_tree(docs_dir, en_path)

    # Генерация документации API
    _generate_api_docs(ru_path, en_path)
    _generate_llms_files(ru_path, "ru", "https://humanitec.ru/documentation/")
    _generate_llms_files(en_path, "en", "https://humanitec.ru/documentation/en/")


if __name__ == "__main__":
    main()
