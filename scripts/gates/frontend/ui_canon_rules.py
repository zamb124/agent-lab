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
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from scripts.gates.kit import REPO_ROOT

Severity = Literal["hard", "soft"]

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
    path_include: str | None = None
    kind: Literal["content", "file"] = "content"
    # Файлы embed-замыкания (внешние сайты без import-map) освобождены от
    # правила. Сейчас ни одно правило не пользуется — npm-канон един для всех.
    exempt_in_embed_closure: bool = False
    # Сканировать код без // и /* */ комментариев (для правил про разметку,
    # где упоминание класса в комментарии — ложное срабатывание).
    strip_comments: bool = False
    # Вырезать содержимое строковых литералов, сохраняя переводы строк.
    # Пример кода внутри шаблонной строки — не вызов console.
    strip_strings: bool = False
    # Искать по всему тексту файла (нужно для тегов, чьи атрибуты живут
    # на нескольких строках — lookahead до `>` не работает построчно).
    multiline: bool = False


RULES: tuple[UiCanonRule, ...] = (
    UiCanonRule(
        "ui_js_files",
        r"\A",
        ("apps", "lib", "tests"),
        "hard",
        "Конвертировать в .ts (strict) — frontend-engineer, recipes.md § 16",
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
    ),
    UiCanonRule(
        "vendored_dep_path",
        r"from\s+['\"][^'\"]*assets/js/(marked|centrifuge)/",
        ("apps", "lib", "tests"),
        "hard",
        "from 'marked' / 'centrifuge' — npm-пакет, не vendored-путь",
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
        # Зеркало check_field_canon.sh: whitelist type=file|hidden|range|color|
        # checkbox|radio|search и data-canon; иначе только <platform-field>.
        # (?=[\s>/]) — чтобы <select-company-page> не совпадал с <select>.
        r"<input(?=[\s>/])(?![^>]*\btype=[\"'](?:file|hidden|range|color|checkbox|radio|search)[\"'])(?![^>]*\bdata-canon=)[^>]*>"
        r"|<textarea(?=[\s>/])(?![^>]*\bdata-canon=)[^>]*>"
        r"|<select(?=[\s>/])(?![^>]*\bdata-canon=)[^>]*>",
        ("apps",),
        "hard",
        "<platform-field> — сырой тег только по whitelist ui_fields.mdc",
        path_exclude=r"check_field_canon|/vendor/|native-app",
        path_include=r"^apps/[^/]+/ui/(pages|modals|components)/",
        multiline=True,
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
        "useDomEvent базы — авто-снятие на disconnect; голые add/removeEventListener-пары и bound-поля под них — отсебятина",
    ),
    UiCanonRule(
        "manual_busy_state",
        r"this\._(busy|loading|saving)\s*=",
        ("apps",),
        "soft",
        "useOp/createForm состояния — ручной _busy дублирует фабрику",
    ),
    UiCanonRule(
        "ts_controller_cast",
        r"this\.use(?:Resource|Op|Form|CursorList|Facets|Slice)\([^)]*\)\s+as\s",
        ("apps", "lib"),
        "hard",
        "тип контроллера выводится из имени фабрики (PlatformFactoryRegistry); поле — ControllerFor<'<svc>/<entity>'>",
        path_include=r"\.ts$",
    ),
    UiCanonRule(
        "ts_explicit_any",
        r"(?::|\bas|<|,|\|)\s*any\b(?![\w$-])|\bany\[\]",
        ("apps", "lib", "tests"),
        "soft",
        "доменный тип или generic фабрики/контроллера; unknown сужается только на typed boundary",
        path_include=r"\.ts$",
        strip_comments=True,
    ),
    UiCanonRule(
        "ts_double_cast",
        r"\bas\s+unknown\s+as\b",
        ("apps", "lib", "tests"),
        "soft",
        "тип чинится в источнике потери (фабрика, контроллер, transport); двойной каст запрещён",
        path_include=r"\.ts$",
        strip_comments=True,
    ),
    UiCanonRule(
        "ts_type_assertion",
        r"^(?!\s*(?:import|export)\b).*\bas\s+(?!const\b)(?:unknown\b|[A-Z{(\[])",
        ("apps", "lib", "tests"),
        "soft",
        "сужение guard-ом или generic контроллера; каст — только event.target DOM-события",
        path_include=r"\.ts$",
        strip_comments=True,
    ),
    UiCanonRule(
        "ts_non_null_assertion",
        r"[\w$)\]]!(?=[.\[)\];,])",
        ("apps", "lib", "tests"),
        "soft",
        "тип без null в контракте или явный throw на отсутствии значения",
        path_include=r"\.ts$",
        strip_comments=True,
    ),
    UiCanonRule(
        "ts_silent_catch",
        r"\bcatch\s*\{",
        ("apps", "lib", "tests"),
        "soft",
        "catch (err) конкретного класса → *_FAILED или throw; catch без привязки выбрасывает ошибку",
        path_include=r"\.ts$",
        strip_comments=True,
    ),
    UiCanonRule(
        "ts_literal_fallback",
        r"(?:\|\||\?\?)\s*(?:''|\"\"|``|\[\]|\{\}|null\b|undefined\b|0\b|false\b|'—')",
        ("apps", "lib", "tests"),
        "soft",
        "дефолт — только initialSlice/extraInitial фабрики; отсутствие обязательного значения — throw",
        path_include=r"\.ts$",
        strip_comments=True,
    ),
    UiCanonRule(
        "ts_console",
        r"\bconsole\.(?:log|info|warn|error|debug)\(",
        ("apps", "lib"),
        "soft",
        "ошибка — throw или *_FAILED фабрики; диагностика — ?platform_devtools=1",
        path_exclude=r"/events/devtools\.ts$",
        path_include=r"\.ts$",
        strip_comments=True,
        strip_strings=True,
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
    "core/frontend/static/lib/embed-flow-ui/flow-ui-embed-autoload.ts",
    "core/frontend/static/lib/flow-ui/shell/embed-autoload.ts",
    "core/frontend/static/lib/embed-chat/linnex-embed-autoload.ts",
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
        if not p.is_file():
            raise FileNotFoundError(f"embed entrypoint not found: {ep}")
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


def _blank_one_string(text: str, start: int) -> tuple[str, int]:
    """Гасит одну строку с позиции открывающей кавычки. Возвращает текст и индекс после неё."""
    quote = text[start]
    out = [quote]
    i = start + 1
    length = len(text)
    while i < length:
        cur = text[i]
        if cur == "\\":
            out.append(" ")
            i += 1
            if i < length:
                out.append("\n" if text[i] == "\n" else " ")
                i += 1
            continue
        if quote == "`" and cur == "$" and i + 1 < length and text[i + 1] == "{":
            out.append("${")
            i += 2
            depth = 1
            while i < length and depth > 0:
                if text[i] in "\"'`":
                    nested, i = _blank_one_string(text, i)
                    out.append(nested)
                    continue
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                out.append(text[i])
                i += 1
            continue
        if cur == quote:
            out.append(cur)
            return "".join(out), i + 1
        out.append("\n" if cur == "\n" else " ")
        i += 1
    return "".join(out), i


def blank_string_literals(text: str) -> str:
    """Заменяет содержимое строк пробелами, переводы строк оставляет."""
    out: list[str] = []
    i = 0
    length = len(text)
    while i < length:
        if text[i] in "\"'`":
            blanked, i = _blank_one_string(text, i)
            out.append(blanked)
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def iter_findings(rule: UiCanonRule) -> list[tuple[Path, str, int, str]]:
    """(path, rel, line_no, line) по правилу."""
    path_ex = re.compile(rule.path_exclude) if rule.path_exclude else None
    path_in = re.compile(rule.path_include) if rule.path_include else None
    embed_ex = embed_closure() if rule.exempt_in_embed_closure else frozenset()
    content_re = re.compile(rule.pattern) if rule.kind == "content" else None
    findings: list[tuple[Path, str, int, str]] = []
    for scope in rule.scopes:
        for path in iter_scope_files(scope):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if path_ex and path_ex.search(rel):
                continue
            if path_in and not path_in.search(rel):
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
            if rule.strip_strings:
                raw_text = blank_string_literals(raw_text)
            if rule.strip_comments:
                raw_text = re.sub(r"//[^\n]*|/\*.*?\*/", "", raw_text, flags=re.S)
            if rule.multiline:
                for m in content_re.finditer(raw_text):
                    line_no = raw_text.count("\n", 0, m.start()) + 1
                    findings.append((path, rel, line_no, m.group(0)[:160].replace("\n", " ")))
                continue
            lines = raw_text.splitlines()
            for i, line in enumerate(lines, 1):
                if content_re.search(line):
                    findings.append((path, rel, i, line.strip()[:160]))
    return findings
