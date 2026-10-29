#!/usr/bin/env python3
"""Отчёт дрейфа `.cursor/rules` относительно кода и канона `rules.mdc`.

Read-only: ничего не пишет. Выход 1, если найдено хотя бы одно нарушение.

Проверяет:
- пути в обратных кавычках (`core/…`, `apps/…`, `scripts/…`, `tests/…`, …) существуют;
- упоминания `<name>.mdc` в правилах, скилах, AGENTS.md, коде, скриптах и доках указывают на существующее правило;
- запрещённые слова вне обратных кавычек;
- frontmatter: description до 200 символов, alwaysApply только у main/architecture, globs доменных правил совпадают с файлами;
- бюджеты размера;
- разделы `##` — только разделы шаблона доменного или сквозного правила и в его порядке;
- ссылки `<name>.mdc § <Раздел>` (в том числе в форме markdown-ссылки) указывают на существующий заголовок;
- количество меток `[без гейта]` (информативно).
"""

from __future__ import annotations

import glob
import re
import sys
from pathlib import Path

REPO = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[4]
RULES = REPO / ".cursor" / "rules"
SKILLS = REPO / ".cursor" / "skills"

PATH_PREFIXES = ("core/", "apps/", "scripts/", "tests/", "migrations/", "deploy/", "mk/", "docs/", ".cursor/")
PATH_RE = re.compile(r"`((?:core|apps|scripts|tests|migrations|deploy|mk|docs|\.cursor)/[^`\s]+)`")
MDC_RE = re.compile(r"(?<![\w/.-])([a-z][a-z0-9_-]*\.mdc)\b")
BACKTICK_RE = re.compile(r"`[^`]*`")
FENCE_RE = re.compile(r"```.*?```", re.S)
URL_RE = re.compile(r"https?://[^\s)]+")
STOP_WORDS = (
    r"желательно", r"рекомендуется", r"по возможности", r"обычно", r"как правило", r"\bстоит\b",
    r"постарайся", r"\blegacy\b", r"\bphase\b", r"\bфаз[аыу]\b", r"\bраньше\b", r"\bтеперь\b",
    r"больше не", r"\bудал[её]н[аоы]?\b", r"\bвременно\b", r"\bбудущ", r"\btodo\b", r"\bдолг\b",
    r"\bv1\b", r"\bэпик", r"\bmvp\b", r"до миграции", r"после миграции",
)
STOP_RE = re.compile("|".join(STOP_WORDS), re.I)
ALWAYS = {"main.mdc", "architecture.mdc"}
LARGE = {
    "flows.mdc", "flows_runtime.mdc", "crm.mdc", "sync.mdc", "files.mdc", "testing.mdc",
    "ui_factories.mdc", "ui_components.mdc",
}
CROSS_CUTTING = {
    "database.mdc", "configuration.mdc", "events.mdc", "authorization.mdc", "logging.mdc",
    "tracing.mdc", "billing.mdc", "taskiq.mdc", "integrations.mdc", "infrastructure.mdc", "testing.mdc",
    "code_search.mdc",
    "scripts.mdc",
}
OUTSIDE_TEMPLATE = {"main.mdc", "architecture.mdc", "rules.mdc"}
DOMAIN_SECTIONS = ("Модель", "Инварианты", "Контракты", "Интеграции", "UI", "Запреты", "Исключения", "Гейты")
CROSS_SECTIONS = ("Модель", "Канон", "Запреты", "Исключения", "Гейты")
H2_RE = re.compile(r"^## (.+?)\s*$", re.M)
HEADING_RE = re.compile(r"^#{2,3} (.+?)\s*$", re.M)
SECTION_REF_RE = re.compile(r"([a-z][a-z0-9_-]*\.mdc)[`*\])]*\s*§\s*«?([^;,.()|:\n`»→—\"*]+)")
PLACEHOLDER_CHARS = set("*{}<>|…")


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


def path_exists(raw: str) -> bool:
    candidate = raw.rstrip(".,:;)").split("::")[0]
    if any(char in candidate for char in PLACEHOLDER_CHARS):
        return True
    return (REPO / candidate).exists()


def main() -> int:
    problems: list[str] = []
    rule_names = {path.name for path in RULES.glob("*.mdc")}
    no_gate_total = 0
    for rule in sorted(RULES.glob("*.mdc")):
        text = rule.read_text(encoding="utf-8")
        meta, body = frontmatter(text)
        name = rule.name
        if "description" not in meta or not meta["description"]:
            problems.append(f"{name}: frontmatter без description")
        elif len(str(meta["description"])) > 200:
            problems.append(f"{name}: description {len(str(meta['description']))} символов > 200")
        always = str(meta.get("alwaysApply", "false")).lower() == "true"
        if always != (name in ALWAYS):
            problems.append(f"{name}: alwaysApply={always}, допустимо true только у main/architecture")
        globs = meta.get("globs", [])
        globs_list = globs if isinstance(globs, list) else [globs]
        if name not in ALWAYS and name not in CROSS_CUTTING and not globs_list:
            problems.append(f"{name}: доменное правило без globs")
        for pattern in globs_list:
            if pattern and not glob.glob(str(REPO / pattern), recursive=True):
                problems.append(f"{name}: glob без совпадений: {pattern}")
        size_bytes = len(text.encode("utf-8"))
        lines = text.count("\n") + 1
        if name == "main.mdc" and size_bytes > 35 * 1024:
            problems.append(f"{name}: {size_bytes} байт > 35KB")
        elif name == "architecture.mdc" and size_bytes > 20 * 1024:
            problems.append(f"{name}: {size_bytes} байт > 20KB")
        elif name not in ALWAYS:
            limit = 220 if name in LARGE else 150
            if lines > limit:
                problems.append(f"{name}: {lines} строк > {limit}")
        for match in PATH_RE.finditer(FENCE_RE.sub("", text)):
            if not path_exists(match.group(1)):
                problems.append(f"{name}: мёртвый путь `{match.group(1)}`")
        plain = URL_RE.sub("", BACKTICK_RE.sub("", FENCE_RE.sub("", body)))
        for line_no, line in enumerate(plain.splitlines(), 1):
            hit = STOP_RE.search(line)
            if hit:
                problems.append(f"{name}: стоп-слово «{hit.group(0)}»: {line.strip()[:120]}")
        no_gate_total += text.count("[без гейта]")
        if name not in OUTSIDE_TEMPLATE:
            allowed = CROSS_SECTIONS if name in CROSS_CUTTING else DOMAIN_SECTIONS
            sections = H2_RE.findall(FENCE_RE.sub("", body))
            unknown = [section for section in sections if section not in allowed]
            if unknown:
                problems.append(f"{name}: разделы вне шаблона: {', '.join(unknown)}")
            ordered = [section for section in sections if section in allowed]
            if ordered != sorted(ordered, key=allowed.index) or len(ordered) != len(set(ordered)):
                problems.append(f"{name}: порядок разделов не по шаблону: {', '.join(ordered)}")
    headings = {
        rule.name: HEADING_RE.findall(FENCE_RE.sub("", rule.read_text(encoding="utf-8")))
        for rule in RULES.glob("*.mdc")
    }
    scan_roots = [SKILLS, REPO / "AGENTS.md", REPO / "scripts", REPO / "core", REPO / "apps", REPO / "tests", REPO / "docs", REPO / "mk", REPO / "mobile", REPO / "README.md", REPO / "Makefile", RULES]
    for root in scan_roots:
        files = [root] if root.is_file() else [p for p in root.rglob("*") if p.is_file()]
        for path in files:
            if any(part in {"node_modules", "vendor", "dist", "__pycache__", ".venv"} for part in path.parts):
                continue
            if path.suffix not in {".md", ".mdc", ".py", ".js", ".sh", ".mk", ".json", ".yaml", ".yml", ".txt", ""}:
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for match in MDC_RE.finditer(content):
                ref = match.group(1)
                if ref not in rule_names:
                    rel = path.relative_to(REPO)
                    problems.append(f"{rel}: ссылка на несуществующее правило {ref}")
            for match in SECTION_REF_RE.finditer(content):
                target, section = match.group(1), match.group(2).strip()
                if target not in headings or not section:
                    continue
                if not any(heading.startswith(section) or section.startswith(heading) for heading in headings[target]):
                    problems.append(f"{path.relative_to(REPO)}: нет раздела «{section}» в {target}")
            if root == SKILLS or path.name == "AGENTS.md":
                for match in PATH_RE.finditer(FENCE_RE.sub("", content)):
                    if not path_exists(match.group(1)):
                        problems.append(f"{path.relative_to(REPO)}: мёртвый путь `{match.group(1)}`")
    for problem in problems:
        print(problem)
    print(f"--- правил: {len(rule_names)}, нарушений: {len(problems)}, меток [без гейта]: {no_gate_total}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
