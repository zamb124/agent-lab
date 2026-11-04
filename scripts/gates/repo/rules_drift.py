#!/usr/bin/env python3
"""Дрейф `.cursor/rules`, скилов и AGENTS.md относительно кода и канона `rules.mdc`.

Read-only. Выход 1, если найдено хотя бы одно нарушение.

Правила: frontmatter (description до 200 символов, alwaysApply только у main/architecture,
globs совпадают с файлами), бюджеты размера, разделы `##` по шаблону, нумерация списков,
символы в обратных кавычках существуют в коде, пары `Symbol (path)` разрешаются,
таблицы `main.mdc` (сервисы и порты, список `core/`, навигация) равны коду.
Правила, скилы, AGENTS.md: пути, `make`-цели, модули `python -m`, маски `*.js` при `.ts` на диске,
запрещённые слова вне обратных кавычек. Любые файлы: `<name>.mdc` и `§ <Раздел>` указывают на существующее.
"""

from __future__ import annotations

import fnmatch
import glob
import os
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from scripts.gates.kit import REPO_ROOT, report
from scripts.gates.registry import GATES

CODE_ROOTS = ("apps", "core", "scripts", "tests", "migrations", "deploy", "mk", "docs", "mobile", "typings", ".github", "ci_scripts")
ROOT_FILES = (
    "Makefile", "README.md", "conf.json", "package.json", "pyproject.toml", "mprocs.yaml", "pytest.ini",
    "tsconfig.json", "tsconfig.base.json", "vitest.config.ts", "web-test-runner.config.ts", "analyze_imports.py",
    "Dockerfile", "Dockerfile.gpu", "docker-compose-dev.yaml", "docker-compose-test.yaml",
)
SKIP_DIRS = frozenset({
    "node_modules", "vendor", "dist", "__pycache__", ".venv", "ui-dist", "embed-dist", "documentation-dist",
    "reports", "data", ".git", ".mypy_cache", ".ruff_cache", ".pytest_cache",
})
INDEX_SUFFIXES = frozenset({
    ".py", ".ts", ".tsx", ".js", ".mjs", ".json", ".yaml", ".yml", ".mk", ".sh", ".tpl", ".md", ".mdc", ".sql",
    ".toml", ".cfg", ".txt", ".html", ".css", "",
})
REF_SUFFIXES = frozenset({".md", ".mdc", ".py", ".js", ".ts", ".sh", ".mk", ".json", ".yaml", ".yml", ".txt", ".tpl", ".toml", ""})

PATH_RE = re.compile(r"`((?:core|apps|scripts|tests|migrations|deploy|mk|docs|\.github|\.cursor)/[^`\s]+)`")
MDC_RE = re.compile(r"(?<![\w/.-])([a-z][a-z0-9_-]*\.mdc)\b")
SECTION_REF_RE = re.compile(r"([a-z][a-z0-9_-]*\.mdc)[`*\])]*\s*§\s*«?([^;,.()|:\n`»→—\"*]+)")
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
BACKTICK_RE = re.compile(r"`[^`\n]*`")
BACKTICK_CAPTURE_RE = re.compile(r"`([^`\n]+)`")
FENCE_RE = re.compile(r"```.*?```", re.S)
URL_RE = re.compile(r"https?://[^\s)]+")
H2_RE = re.compile(r"^## (.+?)\s*$", re.M)
HEADING_RE = re.compile(r"^#{2,3} (.+?)\s*$", re.M)
LIST_ITEM_RE = re.compile(r"^(\d+)\. ")
PAIR_RE = re.compile(r"`([A-Za-z_][\w.]*(?:\([^`]*\))?)`\s*\(`((?:core|apps|scripts|tests)/[^`\s]+)`\)")
MAKE_RE = re.compile(r"\bmake\s+([a-z][a-z0-9_-]*)([*<{]?)")
PYTHON_MODULE_RE = re.compile(r"\bpython3?\s+-m\s+([A-Za-z_][\w.]*)([*<{]?)")
JS_TOKEN_RE = re.compile(r"[A-Za-z0-9_@./*<>{}-]*[A-Za-z0-9_*>}-]\.js\b")
VENDOR_JS_RE = re.compile(r"(\.min\.js|\.esm\.js|bundle\.js)$")
FILE_EXT_RE = re.compile(r"\.(py|ts|js|md|mdc|yaml|yml|json|sh|mk|toml|sql|html|css|txt|png|svg|wav)$")
CALL_RE = re.compile(r"^[A-Za-z_][\w.]*\(")
CAMEL_RE = re.compile(r"^[A-Z][A-Za-z0-9]+[a-z][A-Za-z0-9]*$")
UPPER_RE = re.compile(r"^[A-Z][A-Z0-9_]{4,}$")
PLACEHOLDER_CHARS = frozenset("*{}<>|…$=\\")
PORT_RANGE_RE = re.compile(r"^(\d+)\s*[–-]\s*(\d+)$")
DEFAULT_PORTS_RE = re.compile(r"_default_ports:[^=]*=\s*\{(.*?)\n\s*\}", re.S)

STOP_WORDS = (
    r"желательно", r"рекомендуется", r"по возможности", r"обычно", r"как правило", r"\bстоит\b",
    r"постарайся", r"\blegacy\b", r"\bphase\b", r"\bфаз[аыу]\b", r"\bраньше\b", r"\bтеперь\b",
    r"больше не", r"\bудал[её]н[аоы]?\b", r"\bвременно\b", r"\bбудущ", r"\btodo\b", r"\bдолг\b",
    r"\bv1\b", r"\bэпик", r"\bmvp\b", r"до миграции", r"после миграции",
    r"по-прежнему", r"\bранее\b", r"\bпозже\b", r"\bныне\b", r"\bпрежн", r"\bбывш",
    r"\bстар(?:ый|ая|ое|ые|ых|ого|ому|ым|ом|ую)\b", r"\bустарел", r"\bdeprecated\b", r"\bshim\b",
    r"\bcompat\b", r"hard[- ]?cut", r"\bcutover\b", r"\bпромежуточн", r"\bпереходн", r"обратн\w+ совместим",
)
STOP_RE = re.compile("|".join(STOP_WORDS), re.I)
ALWAYS = frozenset({"main.mdc", "architecture.mdc"})
LARGE = frozenset({
    "flows.mdc", "flows_runtime.mdc", "crm.mdc", "sync.mdc", "files.mdc", "testing.mdc",
    "ui_factories.mdc", "ui_components.mdc",
})
CROSS_CUTTING = frozenset({
    "database.mdc", "configuration.mdc", "events.mdc", "authorization.mdc", "logging.mdc",
    "tracing.mdc", "billing.mdc", "taskiq.mdc", "integrations.mdc", "infrastructure.mdc", "testing.mdc",
    "code_search.mdc", "scripts.mdc",
})
OUTSIDE_TEMPLATE = frozenset({"main.mdc", "architecture.mdc", "rules.mdc"})
DOMAIN_SECTIONS = ("Модель", "Инварианты", "Контракты", "Интеграции", "UI", "Запреты", "Исключения", "Гейты")
CROSS_SECTIONS = ("Модель", "Канон", "Запреты", "Исключения", "Гейты")
MAIN_BUDGET_BYTES = 35 * 1024
ARCHITECTURE_BUDGET_BYTES = 20 * 1024

# Внешние имена: идентификаторы вендоров и MCP-инструментов, которых нет в коде платформы.
EXTERNAL_NAMES = frozenset({
    "FinishAuthorize", "CardData", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "VARCHAR", "on_startup", "on_shutdown",
    "search_graph", "search_code", "trace_path", "query_graph", "get_code_snippet", "get_architecture",
    "get_graph_schema", "qualified_name", "name_pattern", "semantic_query", "available_projects",
    "include_tests", "path_filter", "risk_labels", "data_flow", "cross_service", "extensionFilter",
})
# Примеры в запретах и именовании: образцы запрещённых форм, а не символы кода.
EXAMPLE_NAMES = frozenset({
    "FooDTO", "FooData", "FooResponse", "_FooBody", "temp_", "tenant_id", "tenant_subdomain", "tenant_host",
    "tenant_slug", "space_id", "workspace_id", "org_id", "agent_id", "lowerCamel", "scope_entity",
    "list_records", "get_record", "_forbidden", "_not_found",
})
ALLOWED_NAMES = EXTERNAL_NAMES | EXAMPLE_NAMES


@dataclass(frozen=True)
class CodeScan:
    idents: frozenset[str]
    mdc_refs: tuple[tuple[str, str], ...]
    section_refs: tuple[tuple[str, str, str], ...]
    js_names: frozenset[str]
    ts_names: frozenset[str]


@dataclass
class _ScanAcc:
    idents: set[str] = field(default_factory=set)
    mdc_refs: list[tuple[str, str]] = field(default_factory=list)
    section_refs: list[tuple[str, str, str]] = field(default_factory=list)
    js_names: set[str] = field(default_factory=set)
    ts_names: set[str] = field(default_factory=set)


def frontmatter(text: str) -> tuple[dict[str, str | list[str]], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    head, body = text[4:end], text[end + 5 :]
    meta: dict[str, str | list[str]] = {}
    key = ""
    for line in head.splitlines():
        if re.match(r"^\s+-\s+", line) and key:
            value = re.sub(r"^\s+-\s+", "", line).strip().strip('"').strip("'")
            current = meta.get(key)
            meta[key] = [*current, value] if isinstance(current, list) else [value]
            continue
        match = re.match(r"^(\w+):\s*(.*)$", line)
        if match:
            key, value = match.group(1), match.group(2).strip()
            if value.startswith("[") and value.endswith("]"):
                meta[key] = [item.strip().strip('"').strip("'") for item in value[1:-1].split(",") if item.strip()]
            elif value:
                meta[key] = value.strip('"').strip("'")
            else:
                meta[key] = []
    return meta, body


def prose(text: str) -> str:
    return URL_RE.sub("", BACKTICK_RE.sub("", FENCE_RE.sub("", text)))


def stop_word_errors(label: str, text: str) -> list[str]:
    errors: list[str] = []
    for line in prose(text).splitlines():
        hit = STOP_RE.search(line)
        if hit:
            errors.append(f"{label}: стоп-слово «{hit.group(0)}»: {line.strip()[:120]}")
    return errors


def numbering_errors(label: str, text: str) -> list[str]:
    errors: list[str] = []
    expected = 1
    for line in FENCE_RE.sub("", text).splitlines():
        if line.startswith("#"):
            expected = 1
            continue
        match = LIST_ITEM_RE.match(line)
        if match is None:
            continue
        number = int(match.group(1))
        if number == 1:
            expected = 2
        elif number == expected:
            expected += 1
        else:
            errors.append(f"{label}: нумерация {number} после {expected - 1}: {line[:60]}")
            expected = number + 1
    return errors


def section_errors(name: str, body: str) -> list[str]:
    if name in OUTSIDE_TEMPLATE:
        return []
    allowed = CROSS_SECTIONS if name in CROSS_CUTTING else DOMAIN_SECTIONS
    sections = H2_RE.findall(FENCE_RE.sub("", body))
    errors: list[str] = []
    unknown = [section for section in sections if section not in allowed]
    if unknown:
        errors.append(f"{name}: разделы вне шаблона: {', '.join(unknown)}")
    ordered = [section for section in sections if section in allowed]
    if ordered != sorted(ordered, key=allowed.index) or len(ordered) != len(set(ordered)):
        errors.append(f"{name}: порядок разделов не по шаблону: {', '.join(ordered)}")
    return errors


def path_exists(root: Path, raw: str) -> bool:
    candidate = raw.rstrip(".,:;)").split("::")[0]
    if any(char in candidate for char in PLACEHOLDER_CHARS):
        return True
    return (root / candidate).exists()


def dead_path_errors(root: Path, label: str, text: str) -> list[str]:
    return [
        f"{label}: мёртвый путь `{match.group(1)}`"
        for match in PATH_RE.finditer(FENCE_RE.sub("", text))
        if not path_exists(root, match.group(1))
    ]


def _name_shaped(part: str) -> bool:
    if len(part) < 5 or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part):
        return False
    return bool(CAMEL_RE.match(part) or UPPER_RE.match(part) or ("_" in part and part.lower() == part))


def symbol_errors(label: str, text: str, idents: frozenset[str]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for span in BACKTICK_CAPTURE_RE.findall(FENCE_RE.sub("", text)):
        if any(char in PLACEHOLDER_CHARS for char in span) or "/" in span or span.startswith(("http", "-", ".", "@")):
            continue
        if FILE_EXT_RE.search(span) or (" " in span.strip() and not CALL_RE.match(span)):
            continue
        for part in re.split(r"[.:()\[\],\s]+", span):
            if part in seen or part in ALLOWED_NAMES or not _name_shaped(part) or part in idents:
                continue
            seen.add(part)
            errors.append(f"{label}: символ `{part}` не найден в коде")
    return errors


def _file_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def pair_errors(root: Path, label: str, text: str) -> list[str]:
    errors: list[str] = []
    for match in PAIR_RE.finditer(FENCE_RE.sub("", text)):
        symbol, path_text = match.group(1), match.group(2).split("::")[0].rstrip(".,:;)")
        if any(char in path_text for char in PLACEHOLDER_CHARS):
            continue
        target = root / path_text
        last = re.split(r"[(\s]", symbol)[0].split(".")[-1]
        if len(last) < 3:
            continue
        if target.is_dir():
            found = last == target.name or any(
                last in _file_text(file) for file in target.rglob("*") if file.suffix in {".py", ".ts"} and file.is_file()
            )
        elif target.is_file():
            found = last == target.stem or last in _file_text(target)
        else:
            continue
        if not found:
            errors.append(f"{label}: `{symbol}` не найден в `{path_text}`")
    return errors


def js_mask_errors(label: str, text: str, js_names: frozenset[str], ts_names: frozenset[str]) -> list[str]:
    errors: list[str] = []
    for span in BACKTICK_CAPTURE_RE.findall(FENCE_RE.sub("", text)):
        for match in JS_TOKEN_RE.finditer(span):
            token = match.group(0)
            if token.startswith(("/", "./", "../", "@platform/")) or token == "index.js":
                continue
            if any(part in token for part in ("ui-dist/", "embed-dist/", "documentation-dist/")):
                continue
            name = token.rsplit("/", 1)[-1]
            if VENDOR_JS_RE.search(name):
                continue
            pattern = re.sub(r"<[^>]*>|\{[^}]*\}", "*", name)
            ts_pattern = pattern.removesuffix(".js") + ".ts"
            has_js = any(fnmatch.fnmatchcase(candidate, pattern) for candidate in js_names)
            has_ts = any(fnmatch.fnmatchcase(candidate, ts_pattern) for candidate in ts_names)
            if not has_js and has_ts:
                errors.append(f"{label}: `{token}` — на диске `.ts`")
    return errors


def make_targets(root: Path) -> frozenset[str]:
    targets: set[str] = set()
    files = [root / "Makefile", *sorted((root / "mk").glob("*.mk"))]
    for file in files:
        for line in _file_text(file).splitlines():
            match = re.match(r"^\.PHONY:(.*)$", line)
            if match:
                targets.update(match.group(1).split())
                continue
            match = re.match(r"^([A-Za-z0-9_.%/-]+(?:[ \t]+[A-Za-z0-9_.%/-]+)*)[ \t]*:(?!=)", line)
            if match:
                targets.update(match.group(1).split())
    return frozenset(targets)


def command_errors(root: Path, label: str, text: str, targets: frozenset[str]) -> list[str]:
    errors: list[str] = []
    patterns = [target.replace("%", "*") for target in targets if "%" in target]
    for match in MAKE_RE.finditer(text):
        name, placeholder = match.group(1), match.group(2)
        if placeholder or name in targets or any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns):
            continue
        errors.append(f"{label}: make-цель `{name}` не существует")
    for match in PYTHON_MODULE_RE.finditer(text):
        module, placeholder = match.group(1), match.group(2)
        if placeholder or module.endswith(".") or module.split(".")[0] not in {"scripts", "apps", "core"}:
            continue
        base = root / module.replace(".", "/")
        if not (base.with_suffix(".py").is_file() or (base / "__main__.py").is_file()):
            errors.append(f"{label}: модуль `{module}` не существует")
    return errors


def expand_service_names(cell: str) -> list[str]:
    names: list[str] = []
    prefix = ""
    for raw in cell.split(","):
        part = raw.strip()
        if part.startswith("_"):
            names.append(prefix + part[1:])
            continue
        names.append(part)
        prefix = part.rsplit("_", 1)[0] + "_" if "_" in part else ""
    return names


def section_text(text: str, title: str) -> str:
    match = re.search(rf"^## {re.escape(title)}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    return match.group(1) if match else ""


def service_table(main_text: str) -> dict[str, int]:
    rows: dict[str, int] = {}
    for line in section_text(main_text, "Сервисы и стек").splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 3 or not line.startswith("|") or not re.match(r"^\d", cells[1]):
            continue
        names = expand_service_names(cells[0])
        port_range = PORT_RANGE_RE.match(cells[1])
        if port_range:
            start = int(port_range.group(1))
            for offset, name in enumerate(names):
                rows[name] = start + offset
        else:
            rows[names[0]] = int(cells[1])
    return rows


def default_ports(models_text: str) -> dict[str, int]:
    match = DEFAULT_PORTS_RE.search(models_text)
    if match is None:
        return {}
    return {name: int(port) for name, port in re.findall(r'"([a-z_]+)":\s*(\d+)', match.group(1))}


def core_listed(main_text: str) -> list[str]:
    match = re.search(r"Канон:(.*?)(?:\.\s+[А-ЯA-Z]|\n)", re.sub(r"\([^)]*\)", "", section_text(main_text, "Границы core и apps")), re.S)
    return re.findall(r"`([a-z0-9_]+)`", match.group(1)) if match else []


def core_modules(root: Path) -> set[str]:
    return {
        entry.name.removesuffix(".py")
        for entry in (root / "core").iterdir()
        if not entry.name.startswith("__") and (entry.is_dir() or entry.suffix == ".py")
    }


def table_errors(main_text: str, ports: Mapping[str, int], core_names: Iterable[str], rule_names: Iterable[str]) -> list[str]:
    errors: list[str] = []
    table = service_table(main_text)
    for name, port in sorted(table.items()):
        if name not in ports:
            errors.append(f"main.mdc: сервис `{name}` из таблицы нет в `_default_ports`")
        elif ports[name] != port:
            errors.append(f"main.mdc: порт `{name}` {port} ≠ {ports[name]} в `_default_ports`")
    for name in sorted(set(ports) - set(table)):
        errors.append(f"main.mdc: сервис `{name}` ({ports[name]}) отсутствует в таблице «Сервисы и стек»")
    listed = core_listed(main_text)
    actual = set(core_names)
    for name in sorted(set(listed) - actual):
        errors.append(f"main.mdc: `core/{name}` из списка не существует")
    for name in sorted(actual - set(listed)):
        errors.append(f"main.mdc: `core/{name}` отсутствует в списке модулей core")
    nav = re.findall(r"^\| `([a-z0-9_]+\.mdc)` \|", section_text(main_text, "Навигация"), re.M)
    expected = set(rule_names) - {"main.mdc"}
    for name in sorted(expected - set(nav)):
        errors.append(f"main.mdc: правило `{name}` отсутствует в «Навигации»")
    for name in sorted(set(nav) - expected):
        errors.append(f"main.mdc: «Навигация» ссылается на несуществующее `{name}`")
    for name in sorted({item for item in nav if nav.count(item) > 1}):
        errors.append(f"main.mdc: `{name}` повторяется в «Навигации»")
    return errors


def rule_frontmatter_errors(root: Path, name: str, text: str, meta: Mapping[str, str | list[str]]) -> list[str]:
    errors: list[str] = []
    description = str(meta.get("description", ""))
    if not description:
        errors.append(f"{name}: frontmatter без description")
    elif len(description) > 200:
        errors.append(f"{name}: description {len(description)} символов > 200")
    always = str(meta.get("alwaysApply", "false")).lower() == "true"
    if always != (name in ALWAYS):
        errors.append(f"{name}: alwaysApply={always}, допустимо true только у main/architecture")
    raw_globs = meta.get("globs", [])
    globs = raw_globs if isinstance(raw_globs, list) else [raw_globs]
    if name not in ALWAYS and name not in CROSS_CUTTING and not globs:
        errors.append(f"{name}: доменное правило без globs")
    for pattern in globs:
        if pattern and not glob.glob(str(root / pattern), recursive=True):
            errors.append(f"{name}: glob без совпадений: {pattern}")
    size_bytes = len(text.encode("utf-8"))
    lines = text.count("\n") + 1
    if name == "main.mdc" and size_bytes > MAIN_BUDGET_BYTES:
        errors.append(f"{name}: {size_bytes} байт > 35KB")
    elif name == "architecture.mdc" and size_bytes > ARCHITECTURE_BUDGET_BYTES:
        errors.append(f"{name}: {size_bytes} байт > 20KB")
    elif name not in ALWAYS:
        limit = 220 if name in LARGE else 150
        if lines > limit:
            errors.append(f"{name}: {lines} строк > {limit}")
    return errors


def scan_code(root: Path) -> CodeScan:
    acc = _ScanAcc()
    files: list[Path] = [root / name for name in ROOT_FILES if (root / name).is_file()]
    for top in CODE_ROOTS:
        base = root / top
        if not base.is_dir():
            continue
        for current, dirs, names in os.walk(base):
            dirs[:] = [directory for directory in dirs if directory not in SKIP_DIRS]
            files.extend(Path(current) / name for name in names)
    for path in files:
        suffix = path.suffix
        acc.idents.add(path.stem)
        acc.idents.add(path.parent.name)
        if suffix == ".js":
            acc.js_names.add(path.name)
        elif suffix == ".ts":
            acc.ts_names.add(path.name)
        if suffix not in INDEX_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        acc.idents.update(IDENT_RE.findall(text))
        if suffix not in REF_SUFFIXES:
            continue
        relative = path.relative_to(root).as_posix()
        acc.mdc_refs.extend((relative, ref) for ref in MDC_RE.findall(text))
        acc.section_refs.extend((relative, target, section.strip()) for target, section in SECTION_REF_RE.findall(text))
    return CodeScan(
        frozenset(acc.idents), tuple(acc.mdc_refs), tuple(acc.section_refs),
        frozenset(acc.js_names), frozenset(acc.ts_names),
    )


def ref_errors(
    label: str, text: str, rule_names: frozenset[str], headings: Mapping[str, Sequence[str]],
) -> list[str]:
    errors = [f"{label}: ссылка на несуществующее правило {ref}" for ref in MDC_RE.findall(text) if ref not in rule_names]
    for target, section in SECTION_REF_RE.findall(text):
        errors.extend(_section_ref_error(label, target, section.strip(), headings))
    return errors


def _section_ref_error(label: str, target: str, section: str, headings: Mapping[str, Sequence[str]]) -> list[str]:
    if target not in headings or not section:
        return []
    if any(heading.startswith(section) or section.startswith(heading) for heading in headings[target]):
        return []
    return [f"{label}: нет раздела «{section}» в {target}"]


def skill_frontmatter_errors(root: Path, skill: Path) -> list[str]:
    meta, _ = frontmatter(_file_text(skill))
    label = skill.relative_to(root).as_posix()
    errors: list[str] = []
    if str(meta.get("name", "")) != skill.parent.name:
        errors.append(f"{label}: name не равен имени каталога скила")
    if not meta.get("description"):
        errors.append(f"{label}: frontmatter без description")
    return errors


def ungated_registry_gates(rule_texts: Mapping[str, str], gates: Iterable[tuple[str, Sequence[str]]]) -> list[str]:
    corpus = "\n".join(rule_texts.values())
    result: list[str] = []
    for name, argv in gates:
        script = next((item for item in argv if item.startswith("scripts/")), "")
        module = next((item for item in argv if item.startswith("scripts.")), "")
        if script not in corpus and module.replace(".", "/") + ".py" not in corpus and module not in corpus:
            result.append(name)
    return result


def collect(root: Path = REPO_ROOT) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    rules_dir = root / ".cursor" / "rules"
    rule_texts = {path.name: _file_text(path) for path in sorted(rules_dir.glob("*.mdc"))}
    rule_names = frozenset(rule_texts)
    scan = scan_code(root)
    targets = make_targets(root)
    headings = {name: HEADING_RE.findall(FENCE_RE.sub("", text)) for name, text in rule_texts.items()}
    no_gate_total = 0
    for name, text in rule_texts.items():
        meta, body = frontmatter(text)
        errors += rule_frontmatter_errors(root, name, text, meta)
        errors += dead_path_errors(root, name, text)
        errors += stop_word_errors(name, f"{meta.get('description', '')}\n{body}")
        errors += section_errors(name, body)
        errors += numbering_errors(name, body)
        errors += symbol_errors(name, body, scan.idents)
        errors += pair_errors(root, name, body)
        errors += js_mask_errors(name, body, scan.js_names, scan.ts_names)
        errors += command_errors(root, name, text, targets)
        no_gate_total += text.count("[без гейта]")
    prose_files = [*sorted((root / ".cursor" / "skills").rglob("*.md")), root / "AGENTS.md"]
    for path in prose_files:
        text = _file_text(path)
        label = path.relative_to(root).as_posix()
        errors += dead_path_errors(root, label, text)
        errors += stop_word_errors(label, text)
        errors += pair_errors(root, label, text)
        errors += js_mask_errors(label, text, scan.js_names, scan.ts_names)
        errors += command_errors(root, label, text, targets)
        errors += ref_errors(label, text, rule_names, headings)
        if path.name == "SKILL.md":
            errors += skill_frontmatter_errors(root, path)
    errors += symbol_errors("AGENTS.md", _file_text(root / "AGENTS.md"), scan.idents)
    for name, text in rule_texts.items():
        errors += ref_errors(name, text, rule_names, headings)
    for relative, ref in scan.mdc_refs:
        if ref not in rule_names:
            errors.append(f"{relative}: ссылка на несуществующее правило {ref}")
    for relative, target, section in scan.section_refs:
        errors += _section_ref_error(relative, target, section, headings)
    ports = default_ports(_file_text(root / "core" / "config" / "models.py"))
    errors += table_errors(rule_texts["main.mdc"], ports, core_modules(root), rule_names)
    lint_gates = [(gate.name, gate.argv) for gate in GATES if gate.suites & {"lint", "lint_ts"}]
    infos = [f"info: меток [без гейта]: {no_gate_total}"]
    infos += [f"info: гейт {name} не упомянут в «Гейты» правил" for name in ungated_registry_gates(rule_texts, lint_gates)]
    return sorted(set(errors)), infos


def collect_errors() -> list[str]:
    return collect()[0]


def main() -> int:
    errors, infos = collect()
    for info in infos:
        print(info)
    return report("rules_drift", errors)


if __name__ == "__main__":
    raise SystemExit(main())
