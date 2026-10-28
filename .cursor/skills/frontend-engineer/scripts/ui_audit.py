#!/usr/bin/env python3
"""Discovery UI одним прогоном — очередь рекурсивного цикла frontend-engineer.

Секции отчёта:
  1. tsc         — ошибки `npx tsc -p tsconfig.json`.
  2. Конвейер    — tsc в обязательном пути, сборка UI в dev/test, fail-closed раздача ui-dist.
  3. Сигнатуры   — правила `scripts/ui_canon_rules.py` (hard и soft) по зонам и топ файлов.
  4. Скрытое     — находки, которые прячут исключения правил (embed closure, pragma `ui-canon: allow`).
  5. Слепота     — пути и маски `.js` в гейтах, конфигах, правилах и скилах при `.ts` на диске;
                   наборы суффиксов с `.js` без `.ts`: такой гейт TS-файлы не видит.
  6. Мосты       — переходные резолверы, shim, import map, vendored-копии npm-пакетов.
  7. Без гейта   — нормы `[без гейта]` в UI-правилах.

Отчёт, не гейт: выход 0. Ожидаемый файл или блок отсутствует — исключение: скрипт чинится вместе с кодом.

Запуск: `uv run python .cursor/skills/frontend-engineer/scripts/ui_audit.py [--json <path>] [--top N]`.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from scripts.report_ui_kostyli import scope_of
from scripts.ui_canon_rules import RULES, iter_findings

REPO = Path(__file__).resolve().parents[4]
SELF = Path(__file__).resolve()

UI_ROOTS = (
    REPO / "core/frontend/static/lib",
    *sorted((REPO / "apps").glob("*/ui")),
    REPO / "tests/frontend_core",
    REPO / "tests/ui",
)
SKIP_PARTS = frozenset({"vendor", "node_modules", "ui-dist", "embed-dist", "__pycache__", "assets"})

TOOLING_FILES = (
    REPO / "Makefile",
    REPO / "package.json",
    REPO / "tsconfig.json",
    REPO / "tsconfig.base.json",
    REPO / "vitest.config.mjs",
    REPO / "web-test-runner.config.mjs",
    REPO / "Dockerfile",
    REPO / "AGENTS.md",
)
TOOLING_DIRS: tuple[tuple[Path, tuple[str, ...]], ...] = (
    (REPO / "scripts", (".py", ".sh", ".mjs")),
    (REPO / "mk", (".mk",)),
    (REPO / "core/app", (".py",)),
    (REPO / "apps/frontend/services", (".py",)),
    (REPO / ".cursor/rules", (".mdc",)),
    (REPO / ".cursor/skills", (".md", ".py")),
)

JS_TOKEN = re.compile(r"[A-Za-z0-9_@./*-]*[A-Za-z0-9_*-]\.js\b")
VENDOR_NAME = re.compile(r"(\.min\.js|\.esm\.js|bundle\.js)$")
SUFFIX_SET = re.compile(r"[{(\[]\s*(?:[\"']\.\w+[\"']\s*,\s*)+[\"']\.\w+[\"']\s*,?\s*[})\]]")
SUFFIX_EQ = re.compile(r"suffix\s*==\s*[\"']\.js[\"']")

BRIDGES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("резолвер .js→.ts периода миграции", re.compile(r"\b_?js_or_ts\b")),
    ("мост резолва тестового раннера", re.compile(r"tsSibling|jsToTsSibling|js-to-ts-sibling")),
    ("подмена внутренностей плагина", re.compile(r"\.resolveImport\s*=")),
    ("комментарий о переходном периоде", re.compile(r"[Пп]ериод миграции|при миграции|migration period")),
    ("фолбек точки входа index.ts|index.js", re.compile(r"index\.ts['\"],\s*['\"]index\.js|index\.ts\|index\.js")),
    ("переписывание vendored-путей при сборке", re.compile(r"vendoredDedup|vendoredToNpm")),
    ("shim Lit", re.compile(r"lit-shim")),
    ("импорт vendored-копии npm-пакета", re.compile(r"from\s+['\"][^'\"]*assets/js/(?:lit|marked|centrifuge)/")),
    ("import map при бандле", re.compile(r"type=\"importmap\"")),
)
BRIDGE_SCOPE: tuple[tuple[Path, tuple[str, ...]], ...] = (
    (REPO / "scripts", (".py", ".sh", ".mjs")),
    (REPO / "core/app", (".py",)),
    (REPO / "core/frontend/static/lib", (".ts",)),
    (REPO / "core/frontend/pwa", (".js",)),
    *((ui, (".ts", ".html")) for ui in sorted((REPO / "apps").glob("*/ui"))),
)
BRIDGE_FILES = (REPO / "vitest.config.mjs", REPO / "web-test-runner.config.mjs", REPO / "package.json")

UI_RULES = ("frontend", "ui_factories", "ui_components", "ui_fields", "flow_ui")

Findings = dict[str, list[str]]


@dataclass(frozen=True)
class TscResult:
    exit_code: int
    errors: int
    sample: list[str]


@dataclass(frozen=True)
class RuleSummary:
    severity: str
    count: int
    zones: dict[str, int]
    top_files: dict[str, int]
    fix: str


def rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def require_file(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"ui_audit: ожидаемый файл отсутствует — {rel(path)}")
    return path.read_text(encoding="utf-8")


def require_block(text: str, pattern: str, source: str) -> str:
    match = re.search(pattern, text, flags=re.S | re.M)
    if match is None:
        raise ValueError(f"ui_audit: в {source} не найден блок {pattern!r}")
    return match.group(0)


def iter_files(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    if not root.is_dir():
        raise FileNotFoundError(f"ui_audit: ожидаемый каталог отсутствует — {rel(root)}")
    return sorted(
        p for p in root.rglob("*")
        if p.is_file() and p.suffix in suffixes and not (SKIP_PARTS & set(p.relative_to(REPO).parts))
    )


def ui_source_index() -> tuple[set[str], set[str]]:
    js_names: set[str] = set()
    ts_names: set[str] = set()
    for root in UI_ROOTS:
        for path in iter_files(root, (".js", ".ts")):
            (js_names if path.suffix == ".js" else ts_names).add(path.name)
    return js_names, ts_names


def section_tsc() -> TscResult:
    completed = subprocess.run(
        ["npx", "tsc", "-p", "tsconfig.json", "--pretty", "false"],
        cwd=REPO, capture_output=True, text=True, check=False,
    )
    errors = [line for line in completed.stdout.splitlines() if re.search(r"error TS\d+", line)]
    return TscResult(completed.returncode, len(errors), errors[:20])


GRANIAN_HELM_FILES = ("deploy/helm/agent-lab/values.yaml", "deploy/helm/agent-lab/templates/50-gpu/litserve.yaml")
HELM_CORE_LIB_BEFORE_CORE = re.compile(
    r"- /static/core/lib\n\s*- --static-path-mount\n\s*- core/frontend/embed-dist\n\s*- --static-path-route\n\s*- /static/core\n"
)


def make_target_needs(text: str, target: str, prerequisite: str) -> bool:
    return bool(re.search(rf"^{re.escape(target)}:[^\n]*\b{re.escape(prerequisite)}\b", text, re.M))


def section_pipeline() -> dict[str, bool]:
    lint_mk = require_file(REPO / "mk/lint.mk")
    lint_ts = require_block(lint_mk, r"^lint-ts:.*?(?=^\S|\Z)", "mk/lint.mk")
    lint_file = require_block(lint_mk, r"^lint-file:.*?(?=^\S|\Z)", "mk/lint.mk")
    ui_builder = require_block(require_file(REPO / "Dockerfile"), r"AS ui-builder.*?(?=^FROM |\Z)", "Dockerfile")
    serve = require_block(require_file(REPO / "core/app/spa.py"), r"^def resolve_ui_static_dir\(.*?(?=^def |\Z)", "core/app/spa.py")
    run_py = require_file(REPO / "scripts/run.py")
    helm = [require_file(REPO / path) for path in GRANIAN_HELM_FILES]
    return {
        "tsc в lint-ts (make lint)": bool(re.search(r"ui-typecheck|\btsc\b|typecheck:ui", lint_ts)),
        "tsc в Docker ui-builder": bool(re.search(r"\btsc\b|typecheck:ui", ui_builder)),
        "сборка UI в GPU-образе (Dockerfile.gpu)": bool(
            re.search(r"AS ui-builder[\s\S]*?build:ui", require_file(REPO / "Dockerfile.gpu"))
        ),
        "make app собирает UI (mk/app.mk)": make_target_needs(require_file(REPO / "mk/app.mk"), "app", "ui-build"),
        "esbuild watch в make app (mprocs.yaml)": bool(re.search(r"watch:ui|ui_watch", require_file(REPO / "mprocs.yaml"))),
        "make test-up собирает UI (mk/test.mk)": make_target_needs(require_file(REPO / "mk/test.mk"), "test-up", "ui-build"),
        "make doc собирает UI (импортирует приложения)": make_target_needs(require_file(REPO / "Makefile"), "doc", "ui-build"),
        "make lint <file>.ts": "*.ts)" in lint_file,
        "раздача без ui-dist падает (resolve_ui_static_dir)": "raise" in serve and "return ui_dir" not in serve,
        "granian раздаёт ui-dist, а не исходники ui/ (run.py, Helm)": not re.search(r'"apps/\w+/ui"\)', run_py)
        and not any(re.search(r"^\s*- apps/\w+/ui$", text, re.M) for text in helm),
        "embed-dist на /static/core/lib раньше /static/core (run.py, Helm)": run_py.count("CORE_FRONTEND_EMBED,")
        == run_py.count("CORE_FRONTEND_STATIC,")
        > 0
        and all(len(HELM_CORE_LIB_BEFORE_CORE.findall(text)) == len(re.findall(r"- /static/core\n", text)) for text in helm),
    }


def section_signatures(top: int) -> dict[str, RuleSummary]:
    out: dict[str, RuleSummary] = {}
    for rule in sorted(RULES, key=lambda r: (r.severity != "hard", r.rule_id)):
        findings = iter_findings(rule)
        if not findings:
            continue
        zones = Counter(scope_of(path) for _, path, _, _ in findings)
        files = Counter(path for _, path, _, _ in findings)
        out[rule.rule_id] = RuleSummary(rule.severity, len(findings), dict(zones.most_common()), dict(files.most_common(top)), rule.fix)
    return out


def section_hidden() -> Findings:
    hidden: Findings = {}
    for rule in RULES:
        if not rule.exempt_in_embed_closure:
            continue
        shown = {(path, line) for _, path, line, _ in iter_findings(rule)}
        unexempted = replace(rule, exempt_in_embed_closure=False)
        extra = [f"{path}:{line}" for _, path, line, _ in iter_findings(unexempted) if (path, line) not in shown]
        if extra:
            hidden[f"{rule.rule_id} (embed closure)"] = extra
    pragma = re.compile(r"ui-canon:\s*allow\s+(\w+)")
    for root in UI_ROOTS:
        for path in iter_files(root, (".js", ".ts")):
            for match in pragma.finditer(path.read_text(encoding="utf-8")):
                hidden.setdefault(f"{match.group(1)} (pragma)", []).append(rel(path))
    return hidden


def blind_verdict(token: str, js_names: set[str], ts_names: set[str]) -> str | None:
    """Вердикт для пути, имени или маски файла; спецификатор импорта (`@platform/lib/x.js`, `./x.js`) — канон TS ESM."""
    name = token.rsplit("/", 1)[-1]
    if token.startswith(("/", "./", "../", "@platform/")) or VENDOR_NAME.search(name) or token == "index.js":
        return None
    if "*" in token:
        pattern = token if "/" in token else f"**/{token}"
        ts_pattern = pattern.removesuffix(".js") + ".ts"
        bases = (REPO,) if "/" in token and not token.startswith("**") else UI_ROOTS
        js_hits = sum(1 for base in bases for p in base.glob(pattern) if not (SKIP_PARTS & set(p.parts)))
        ts_hits = sum(1 for base in bases for p in base.glob(ts_pattern) if not (SKIP_PARTS & set(p.parts)))
        return "маска находит только .ts" if js_hits == 0 and ts_hits > 0 else None
    if "/" in token:
        for base in (REPO, REPO / "core/frontend/static/lib"):
            js_path = base / token
            if not js_path.exists() and js_path.with_suffix(".ts").exists():
                return "путь .js, на диске .ts"
        return None
    if name not in js_names and name.removesuffix(".js") + ".ts" in ts_names:
        return "имя .js, на диске .ts"
    return None


def section_blind() -> Findings:
    js_names, ts_names = ui_source_index()
    files = [p for p in TOOLING_FILES if p.is_file()]
    for root, suffixes in TOOLING_DIRS:
        files.extend(iter_files(root, suffixes))
    found: Findings = defaultdict(list)
    for path in files:
        if path.resolve() == SELF:
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            where = f"{rel(path)}:{line_no}"
            for match in JS_TOKEN.finditer(line):
                verdict = blind_verdict(match.group(0), js_names, ts_names)
                if verdict:
                    found[verdict].append(f"{where}: {match.group(0)}")
            if path.suffix in (".py", ".sh", ".mjs"):
                for match in SUFFIX_SET.finditer(line):
                    if re.search(r"[\"']\.js[\"']", match.group(0)) and not re.search(r"[\"']\.ts[\"']", match.group(0)):
                        found["набор суффиксов без .ts"].append(f"{where}: {match.group(0)[:80]}")
                # Резолвер TS-спецификатора `./x.js` -> `x.ts` — штатная семантика модулей, не слепое место.
                if SUFFIX_EQ.search(line) and 'with_suffix(".ts")' not in line:
                    found["сравнение suffix == .js"].append(f"{where}: {line.strip()[:80]}")
    return dict(found)


def section_bridges() -> Findings:
    files = [p for p in BRIDGE_FILES if p.is_file()]
    for root, suffixes in BRIDGE_SCOPE:
        files.extend(iter_files(root, suffixes))
    found: Findings = defaultdict(list)
    for path in files:
        if path.resolve() == SELF:
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for label, pattern in BRIDGES:
                if pattern.search(line):
                    found[label].append(f"{rel(path)}:{line_no}")
    return dict(found)


def section_ungated() -> dict[str, int]:
    return {f"{name}.mdc": require_file(REPO / ".cursor/rules" / f"{name}.mdc").count("[без гейта]") for name in UI_RULES}


def print_findings(title: str, items: Findings, top: int) -> None:
    print(f"\n== {title}: {sum(len(v) for v in items.values())}")
    for label, lines in sorted(items.items(), key=lambda kv: -len(kv[1])):
        print(f"  {label}: {len(lines)}")
        for line in lines[:top]:
            print(f"    {line}")


class Args(argparse.Namespace):
    json: Path | None = None
    top: int = 5


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    _ = parser.add_argument("--json", type=Path, help="записать полный отчёт в JSON")
    _ = parser.add_argument("--top", type=int, default=5, help="сколько строк печатать на пункт")
    args = parser.parse_args(namespace=Args())

    tsc = section_tsc()
    pipeline = section_pipeline()
    signatures = section_signatures(args.top)
    hidden = section_hidden()
    blind = section_blind()
    bridges = section_bridges()
    ungated = section_ungated()

    print(f"== tsc: exit={tsc.exit_code} errors={tsc.errors}")
    for line in tsc.sample:
        print(f"    {line}")
    print("\n== Конвейер")
    for label, ok in pipeline.items():
        print(f"  {'OK  ' if ok else 'FAIL'} {label}")
    print("\n== Сигнатуры канона (scripts/ui_canon_rules.py)")
    for rule_id, summary in signatures.items():
        zones = ", ".join(f"{zone}={n}" for zone, n in list(summary.zones.items())[:6])
        print(f"  [{summary.severity}] {rule_id}: {summary.count}  ({zones})")
        for path, n in summary.top_files.items():
            print(f"      {n:5d}  {path}")
    print_findings("Скрытые исключениями находки", hidden, args.top)
    print_findings("Слепые ссылки гейтов, конфигов и правил", blind, args.top)
    print_findings("Мосты", bridges, args.top)
    print(f"\n== Нормы [без гейта]: {sum(ungated.values())}  " + ", ".join(f"{k}={v}" for k, v in ungated.items()))

    if args.json:
        report = {
            "tsc": asdict(tsc),
            "pipeline": pipeline,
            "signatures": {rule_id: asdict(summary) for rule_id, summary in signatures.items()},
            "hidden": hidden,
            "blind": blind,
            "bridges": bridges,
            "ungated": ungated,
        }
        args.json.parent.mkdir(parents=True, exist_ok=True)
        _ = args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\nui_audit: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
