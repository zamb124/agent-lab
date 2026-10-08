"""UI canon rules — единый источник сигнатур «отсебятины» для гейта и отчёта.

Каждое правило: regex по содержимому `.js`/`.ts` файлов в скоупе + метаданные
замены. `severity`:
  - `hard` — ratchet-счётчик (`ui_canon_baseline.json`), рост = FAIL; цель 0.
  - `soft` — только отчёт `report_ui_kostyli.py` (очередь рекурсивного цикла),
    сигнал шумный — перед hard-статусом нужен точный детектор.

Scope-строки: `apps` = apps/*/ui/**; `lib` = core/frontend/static/lib/**;
`tests` = tests/frontend_core/**, tests/ui/**.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

Severity = Literal["hard", "soft"]

REPO_ROOT = Path(__file__).resolve().parent.parent

UI_SCOPES: dict[str, tuple[str, ...]] = {
    "apps": ("apps",),
    "lib": ("core/frontend/static/lib",),
    "tests": ("tests/frontend_core", "tests/ui"),
}

_SKIP_PARTS = frozenset({"vendor", "node_modules", "ui-dist", "desktop", "__pycache__", "dist"})


@dataclass(frozen=True)
class UiCanonRule:
    rule_id: str
    pattern: str
    scopes: tuple[str, ...]
    severity: Severity
    fix: str
    path_exclude: str | None = None
    kind: Literal["content", "file"] = "content"
    # Файлы embed-замыкания (внешние сайты без import-map) освобождены от
    # правила — там относительные пути к assets/js/* каноничны.
    exempt_in_embed_closure: bool = False
    # Сканировать код без // и /* */ комментариев (для правил про разметку,
    # где упоминание класса в комментарии — ложное срабатывание).
    strip_comments: bool = False


RULES: tuple[UiCanonRule, ...] = (
    UiCanonRule(
        "ui_js_files",
        r"\A",
        ("apps", "lib", "tests"),
        "hard",
        "Конвертировать в .ts (strict) — см. frontend-engineer § Рекурсивный цикл",
        kind="file",
        path_exclude=r"\.(ts|mjs)$",
    ),
    UiCanonRule(
        "fetch_outside_events",
        r"\bfetch\(|\bhttpRequest\(",
        ("apps",),
        "hard",
        "Фабрика (useOp/useResource/…) — HTTP/WS вне events/factories|effects|resources запрещён",
        path_exclude=r"/events/(factories|effects|resources)/",
    ),
    UiCanonRule(
        "window_dialogs",
        r"\bwindow\.(confirm|alert|prompt)\(|(?<![.\w])(confirm|prompt)\(|(?<![.\w'\"])\balert\(",
        ("apps", "lib"),
        "hard",
        "platformConfirm/platformPrompt из platform-confirm-modal; результат — toast()",
        # platform-confirm-modal — сам примитив; flow-ui/blocks — методы
        # грамматики блоков (alert(block, ctx)), не window.alert.
        path_exclude=r"platform-confirm-modal|flow-ui/blocks/",
    ),
    UiCanonRule(
        "createelement_modal",
        r"document\.createElement\([^)]*-modal|appendChild\([^)]*modal",
        ("apps",),
        "hard",
        "this.openModal(Kind, props) — модалку открывает только стек",
    ),
    UiCanonRule(
        "localstorage_raw",
        r"\blocalStorage\.(getItem|setItem|removeItem)\(",
        ("apps", "lib"),
        "hard",
        "platformStorageKey(...) + обёртки utils — прямой ключ запрещён",
        path_exclude=r"platform-storage|storage-keys|storage\.effect|native-app-shell|pwa\.effect|platform-brand",
    ),
    UiCanonRule(
        "vendored_lit_path",
        r"from\s+['\"][^'\"]*assets/js/lit/",
        ("apps", "lib", "tests"),
        "hard",
        "from 'lit' / 'lit/directives/*' — vendored-путь дублирует модули",
        exempt_in_embed_closure=True,
    ),
    UiCanonRule(
        "vendored_dep_path",
        r"from\s+['\"][^'\"]*assets/js/(marked|centrifuge)/",
        ("apps", "lib", "tests"),
        "hard",
        "from 'marked' / 'centrifuge' — npm-пакет, не vendored-путь",
        exempt_in_embed_closure=True,
    ),
    UiCanonRule(
        "extends_native",
        r"extends\s+(LitElement|HTMLElement)\b",
        ("apps",),
        "hard",
        "extends PlatformElement/PlatformPage/PlatformModal — LitElement/HTMLElement напрямую запрещены",
    ),
    UiCanonRule(
        "custom_primitive",
        # Только «чистые» UI-примитивы: modal/tabs/menu/table — канонические
        # kind-регистрации или доменные имена (flows-x-modal — не нарушение).
        r"customElements\.define\(\s*['\"][\w-]*(dropdown|tooltip|popover|dialog|checkbox|radio|switch|slider|toast|spinner|skeleton|badge|avatar|chip)[\w-]*['\"]",
        ("apps",),
        "hard",
        "Примитив — только в core UI Kit (lib/components); в apps — композиция kit",
    ),
    UiCanonRule(
        "raw_controls",
        r"<(input|textarea|select)\b",
        ("apps",),
        "hard",
        "<platform-field> — сырой тег только по whitelist ui_fields.mdc",
        path_exclude=r"check_field_canon|/vendor/|native-app",
    ),
    UiCanonRule(
        "manual_pill",
        # Только контейнер pill: `field-pill`, `field-pill-float`, `field-pill--*`.
        # Части внутри shell (field-pill-input, field-pill-file-ref-*, …) — легитимные shared-классы.
        r"""field-pill(?:-float\b|--[\w-]+|(?=[\s"'`}]))""",
        ("apps",),
        "hard",
        "platform-field-shell / platform-field — ручная pill-разметка запрещена",
        strip_comments=True,
    ),
    UiCanonRule(
        "raw_dispatch_events",
        # Только события, у которых есть helper базы (toast/openModal/navigate/…).
        # Доменный dispatch(CoreEvents.X) без хелпера — канон контракта событий.
        r"\.dispatch\(CoreEvents\.(UI_TOAST_SHOW|UI_MODAL_OPEN|UI_MODAL_CLOSE|UI_SIDEBAR_\w+|UI_BOTTOM_SHEET_\w+|UI_CLIPBOARD_\w+|ROUTER_NAVIGATE_REQUESTED|THEME_SET_REQUESTED|I18N_LOCALE_REQUESTED|AUTH_COMPANY_SWITCH_REQUESTED)\b",
        ("apps",),
        "hard",
        "helpers базы (this.toast/navigate/openModal/…) — прямой dispatch запрещён в apps",
        path_exclude=r"/events/|bridge",
    ),
    UiCanonRule(
        "window_custom_event",
        r"window\.dispatchEvent\(new CustomEvent",
        ("apps", "lib"),
        "hard",
        "EventBus/фабрики — window.dispatchEvent запрещён",
    ),
    UiCanonRule(
        "hex_colors",
        r"#[0-9a-fA-F]{3,8}\b|rgba?\(\s*\d",
        ("apps",),
        "soft",
        "tokens.css — литеральные цвета вне токенов запрещены (искл. data-URI/svg)",
        path_exclude=r"\.svg|logo|gradient-map",
    ),
    UiCanonRule(
        "innerhtml_raw",
        r"\.innerHTML\s*=|insertAdjacentHTML\(",
        ("apps", "lib"),
        "soft",
        "lit html``/unsafeHTML с явной причиной — innerHTML наружу уязвим",
    ),
    UiCanonRule(
        "setinterval_poll",
        r"setInterval\(",
        ("apps",),
        "soft",
        "Push через фабрику/EventBus — поллинг только с явной причиной в коде",
    ),
    UiCanonRule(
        "window_listeners",
        r"(window|document)\.addEventListener\(",
        ("apps",),
        "soft",
        "useEvent/handleEvent базы — глобальные listeners вне helpers — отсебятина",
    ),
    UiCanonRule(
        "manual_busy_state",
        r"this\._(busy|loading|saving)\s*=",
        ("apps",),
        "soft",
        "useOp/createForm состояния — ручной _busy дублирует фабрику",
    ),
)


def iter_scope_files(scope: str) -> list[Path]:
    files: list[Path] = []
    for root in UI_SCOPES[scope]:
        base = REPO_ROOT / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in (".js", ".ts", ".mjs"):
                continue
            if _SKIP_PARTS & set(path.parts):
                continue
            files.append(path)
    return files


_EMBED_ENTRYPOINTS = (
    "core/frontend/static/lib/embed-flow-ui/flow-ui-embed-autoload.js",
    "core/frontend/static/lib/flow-ui/shell/embed-autoload.js",
    "core/frontend/static/lib/embed-chat/humanitec-embed-autoload.js",
)

_EMBED_IMPORT_RE = re.compile(
    r"""(?:import|export)[^'"]*?from\s*['"]([^'"]+)['"]"""
    r"""|import\s*['"]([^'"]+)['"]"""
    r"""|import\(\s*['"]([^'"]+)['"]\s*\)"""
)

_embed_closure_cache: frozenset[str] | None = None


def embed_closure() -> frozenset[str]:
    """Файлы, загружаемые на внешних сайтах без import-map (embed-автолоады)."""
    global _embed_closure_cache
    if _embed_closure_cache is not None:
        return _embed_closure_cache
    from collections import deque

    static_root = (REPO_ROOT / "core/frontend/static").resolve()
    visited: set[Path] = set()
    q: deque[Path] = deque()
    for ep in _EMBED_ENTRYPOINTS:
        p = (REPO_ROOT / ep).resolve()
        if p.is_file():
            visited.add(p)
            q.append(p)
    while q:
        cur = q.popleft()
        text = cur.read_text(encoding="utf-8")
        text = re.sub(r"//[^\n]*|/\*.*?\*/", "", text, flags=re.S)
        for m in _EMBED_IMPORT_RE.finditer(text):
            spec = next((g for g in m.groups() if g), None)
            if spec is None or not spec.startswith((".", "/")):
                continue
            tgt = (cur.parent / spec).resolve()
            if tgt.suffix == ".js" and not tgt.exists() and tgt.with_suffix(".ts").exists():
                tgt = tgt.with_suffix(".ts")
            if not tgt.exists() or tgt in visited:
                continue
            try:
                tgt.relative_to(static_root)
            except ValueError:
                continue
            visited.add(tgt)
            q.append(tgt)
    _embed_closure_cache = frozenset(
        p.relative_to(REPO_ROOT).as_posix() for p in visited
    )
    return _embed_closure_cache


def iter_findings(rule: UiCanonRule) -> list[tuple[Path, str, int, str]]:
    """(path, rel, line_no, line) по правилу."""
    path_ex = re.compile(rule.path_exclude) if rule.path_exclude else None
    embed_ex = embed_closure() if rule.exempt_in_embed_closure else frozenset()
    content_re = re.compile(rule.pattern) if rule.kind == "content" else None
    findings: list[tuple[Path, str, int, str]] = []
    for scope in rule.scopes:
        for path in iter_scope_files(scope):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if path_ex and path_ex.search(rel):
                continue
            if rel in embed_ex:
                continue
            if rule.kind == "file":
                findings.append((path, rel, 0, rel))
                continue
            assert content_re is not None
            try:
                raw_text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            # Файл-pragma: `// ui-canon: allow <rule_id>` — осознанное исключение
            # (легитимный кейс, задокументированный в коде).
            if re.search(rf"ui-canon:\s*allow\s+{re.escape(rule.rule_id)}\b", raw_text):
                continue
            if rule.strip_comments:
                raw_text = re.sub(r"//[^\n]*|/\*.*?\*/", "", raw_text, flags=re.S)
            lines = raw_text.splitlines()
            for i, line in enumerate(lines, 1):
                if content_re.search(line):
                    findings.append((path, rel, i, line.strip()[:160]))
    return findings
