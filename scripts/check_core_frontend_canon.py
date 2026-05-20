#!/usr/bin/env python3
"""
Канон core/frontend/static/lib/** — статическая проверка соответствия
event-архитектуре. Запускается как первый слой Layer 1 перед запуском
любых browser/unit тестов и блокирует CI.

Зоны:

  events/**       — фундамент (bus, log, contract, factory-registry,
                    select-controller, http, ws.effect, factories/, reducers/,
                    effects/). Здесь не место LitElement, BaseStore, fetch
                    вне http.js/effects, |/?? фолбекам в reducers/factories.

  base/**         — PlatformElement / PlatformApp / PlatformPage /
                    use-resource. Все публичные методы PlatformElement обязаны
                    бросать Error при отсутствии обязательных аргументов.

  components/**   — UI Kit; extends ТОЛЬКО PlatformElement / PlatformModal /
                    PlatformFormModal. Каждая модалка
                    обязана иметь static modalKind + парный registerModalKind.

  utils/**        — pure helpers; запрещены импорты из apps/ и работа с fetch.

Парсинг — regex, без AST. Это сознательный компромисс ради простоты и
скорости (как scripts/check_ui_canon.sh / check_ui_factories.py).

Запуск:
    uv run python scripts/check_core_frontend_canon.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "core" / "frontend" / "static" / "lib"

EXCLUDED_DIRS = {"embed-chat"}

ALLOWED_EVENT_TYPE = re.compile(r"^[a-z][a-z0-9_]*(\/[a-z][a-z0-9_]*){2,}$")

ERRORS: list[str] = []


def fail(message: str) -> None:
    ERRORS.append(message)


def _iter_js(*subdirs: str) -> list[Path]:
    files: list[Path] = []
    for sub in subdirs:
        root = LIB / sub
        if not root.exists():
            continue
        for path in root.rglob("*.js"):
            parts = set(path.relative_to(LIB).parts)
            if parts & EXCLUDED_DIRS:
                continue
            files.append(path)
    return sorted(files)


def _strip_comments(text: str) -> str:
    """Грубо вырезать /* ... */ и //... комментарии, сохраняя номера строк."""
    def _block(match: re.Match[str]) -> str:
        return "\n" * match.group(0).count("\n")

    text = re.sub(r"/\*.*?\*/", _block, text, flags=re.S)
    text = re.sub(r"(^|[^:\\])//[^\n]*", lambda m: m.group(1), text)
    return text


def _check_no_pattern(files: list[Path], pattern: re.Pattern[str], message: str) -> None:
    for path in files:
        text = path.read_text(encoding="utf-8")
        clean = _strip_comments(text)
        for match in pattern.finditer(clean):
            line = clean[: match.start()].count("\n") + 1
            fail(f"{path.relative_to(ROOT)}:{line}: {message} -> {match.group(0).strip()[:120]}")


def check_events_zone() -> None:
    files = _iter_js("events")
    if not files:
        fail("core/frontend/static/lib/events/** is empty?")
        return

    _check_no_pattern(
        files,
        re.compile(r"\bextends\s+(LitElement|HTMLElement)\b"),
        "events/** must not extend LitElement / HTMLElement",
    )
    _check_no_pattern(
        files,
        re.compile(r"\b(BaseStore|BaseService|ServiceRegistry|AppEvents|Zustand)\b"),
        "events/** must not reference legacy primitives",
    )
    # fetch разрешён только в http.js (низкоуровневый клиент) и в effects/* (effects
    # сами знают, как обращаться с сетью — http.js или прямой fetch на статику/SSE).
    for path in files:
        rel = path.relative_to(LIB / "events")
        text = _strip_comments(path.read_text(encoding="utf-8"))
        first_part = rel.parts[0] if rel.parts else ""
        if re.search(r"\bfetch\s*\(", text):
            if path != LIB / "events" / "http.js" and first_part != "effects":
                fail(f"{path.relative_to(ROOT)}: fetch( is allowed only in events/http.js and events/effects/")
        if re.search(r"\bnew\s+WebSocket\s*\(", text) and first_part != "effects":
            fail(f"{path.relative_to(ROOT)}: new WebSocket allowed only in events/effects/")

    # Reducers и factories — без `|| []`, `|| {}`, `?? null`, `?? '...'` фолбеков
    # (см. ui_factories.mdc «Запрет фолбеков»). Внутренние утилиты (_internal,
    # _transport, register) исключены, у них нет state-чтения.
    fallback_zones = [
        LIB / "events" / "reducers",
        LIB / "events" / "factories",
    ]
    fallback_files = [p for p in files if any(str(p).startswith(str(z)) for z in fallback_zones)]
    fallback_excluded = {
        LIB / "events" / "factories" / "_internal.js",
        LIB / "events" / "factories" / "_transport.js",
        LIB / "events" / "factories" / "register.js",
    }
    fallback_pattern = re.compile(r"\)\s*\|\|\s*(\[\]|\{\}|null)|\?\?\s*(\[\]|\{\}|null|['\"][^'\"]*['\"])")
    for path in fallback_files:
        if path in fallback_excluded:
            continue
        text = _strip_comments(path.read_text(encoding="utf-8"))
        for match in fallback_pattern.finditer(text):
            line = text[: match.start()].count("\n") + 1
            fail(
                f"{path.relative_to(ROOT)}:{line}: fallback `|| [] | || {{}} | ?? ...` запрещён в reducers/factories — проверяйте payload явно и бросайте"
            )

    contract_path = LIB / "events" / "contract.js"
    contract_text = contract_path.read_text(encoding="utf-8")
    block = re.search(r"export\s+const\s+CoreEvents\s*=\s*Object\.freeze\(\{(?P<body>[^}]+)\}", contract_text, re.S)
    if not block:
        fail(f"{contract_path.relative_to(ROOT)}: cannot locate CoreEvents block")
    else:
        for m in re.finditer(r"['\"]([^'\"]+)['\"]", block.group("body")):
            value = m.group(1)
            if not ALLOWED_EVENT_TYPE.match(value):
                fail(f"{contract_path.relative_to(ROOT)}: CoreEvents value '{value}' violates contract <scope>/<entity>/<verb>")


def check_base_zone() -> None:
    files = _iter_js("base", "platform-element")
    if not files:
        fail("core/frontend/static/lib/{base,platform-element} is empty?")
        return
    _check_no_pattern(
        files,
        re.compile(r"\bextends\s+(LitElement|HTMLElement)\b"),
        "base/** must not extend LitElement directly (PlatformElement is the only LitElement child)",
    ) if False else None  # PlatformElement legitimately extends LitElement

    # Только в самом PlatformElement допускается `extends LitElement`.
    pe_path = LIB / "platform-element" / "index.js"
    for path in files:
        if path == pe_path:
            continue
        text = _strip_comments(path.read_text(encoding="utf-8"))
        if re.search(r"\bextends\s+LitElement\b", text):
            fail(f"{path.relative_to(ROOT)}: only platform-element/index.js may extend LitElement")

    _check_no_pattern(
        files,
        re.compile(r"\b(BaseStore|BaseService|ServiceRegistry|AppEvents|Zustand)\b"),
        "base/** must not reference legacy primitives",
    )

    text = pe_path.read_text(encoding="utf-8")
    helpers = (
        "dispatch",
        "useEvent",
        "t",
        "useResource",
        "useOp",
        "useForm",
        "useCursorList",
        "useFacets",
        "toast",
        "openModal",
        "closeModal",
        "openBottomSheet",
        "closeBottomSheet",
        "navigate",
        "copyToClipboard",
        "setLocale",
        "setTheme",
        "switchCompany",
    )
    for helper in helpers:
        pattern = rf"\b{re.escape(helper)}\s*\([^)]*\)\s*\{{"
        if not re.search(pattern, text):
            fail(f"PlatformElement: helper '{helper}' missing")
    if "throw new Error" not in text:
        fail("PlatformElement helpers must guard arguments with throw new Error()")


def check_components_zone() -> None:
    files = _iter_js("components")
    if not files:
        fail("core/frontend/static/lib/components is empty?")
        return

    allowed_bases = {
        "PlatformElement",
        "PlatformModal",
        "PlatformFormModal",
        "PlatformBottomSheet",
    }
    extends_pattern = re.compile(r"class\s+(\w+)\s+extends\s+(\w+)\b")
    for path in files:
        text = _strip_comments(path.read_text(encoding="utf-8"))
        for match in extends_pattern.finditer(text):
            child, parent = match.group(1), match.group(2)
            if parent not in allowed_bases:
                fail(
                    f"{path.relative_to(ROOT)}: {child} extends {parent} — components/** должны наследовать "
                    f"только {sorted(allowed_bases)}"
                )

    # Concrete-модалки (`customElements.define`) ОБЯЗАНЫ иметь static modalKind +
    # registerModalKind. Базовые модалки UI Kit (glass-modal / glass-form-modal,
    # platform-modal-stack, platform-confirm-modal — абстрактный базовый класс
    # для apps) — исключены.
    base_modals = {
        "glass-modal.js",
        "glass-form-modal.js",
        "platform-modal-stack.js",
        "platform-confirm-modal.js",  # абстрактный родитель для apps/<svc>/ui/modals/confirm-modal.js
    }
    legacy_modals = {
        "file-text-preview-modal.js",  # known legacy: BaseService + I18nNs, ждёт миграции
    }
    modal_files = [
        p for p in files
        if "modal" in p.name and p.name not in base_modals and p.name not in legacy_modals
    ]
    for path in modal_files:
        text = path.read_text(encoding="utf-8")
        if "customElements.define" not in text:
            continue  # абстрактный базовый класс без concrete-регистрации
        if "static modalKind" not in text:
            fail(f"{path.relative_to(ROOT)}: модалка обязана иметь `static modalKind = '<scope>.<entity>'`")
        if "registerModalKind(" not in text:
            fail(f"{path.relative_to(ROOT)}: модалка обязана вызвать registerModalKind(<kind>, <tag>)")

    # Bottom sheets (mobile shell 2026): concrete-классы (`customElements.define`)
    # ОБЯЗАНЫ иметь `static bottomSheetKind = '<scope>.<entity>'` + парный
    # `registerBottomSheetKind`. Базовые компоненты исключены.
    base_sheets = {
        "platform-bottom-sheet.js",          # базовый класс
        "platform-bottom-sheet-stack.js",    # рендерер стека
    }
    sheet_files = [
        p for p in files
        if ("bottom-sheet" in p.name or p.name.endswith("-sheet.js"))
        and p.name not in base_sheets
    ]
    for path in sheet_files:
        text = path.read_text(encoding="utf-8")
        if "customElements.define" not in text:
            continue
        if "static bottomSheetKind" not in text:
            fail(f"{path.relative_to(ROOT)}: bottom-sheet обязан иметь `static bottomSheetKind = '<scope>.<entity>'`")
        if "registerBottomSheetKind(" not in text:
            fail(f"{path.relative_to(ROOT)}: bottom-sheet обязан вызвать registerBottomSheetKind(<kind>, <tag>)")


def check_utils_zone() -> None:
    files = _iter_js("utils")
    if not files:
        return
    _check_no_pattern(
        files,
        re.compile(r"from\s+['\"][^'\"]*\bapps/"),
        "utils/** must not import from apps/",
    )
    # fetch разрешён только для статических ассетов (CSS-стили — style-cache).
    fetch_allowed = {LIB / "utils" / "style-cache.js"}
    for path in files:
        if path in fetch_allowed:
            continue
        text = _strip_comments(path.read_text(encoding="utf-8"))
        if re.search(r"\bfetch\s*\(", text):
            fail(f"{path.relative_to(ROOT)}: fetch( in utils/** разрешён только в style-cache.js (CSS loader)")


def main() -> int:
    if not LIB.exists():
        print(f"check_core_frontend_canon: {LIB} not found", file=sys.stderr)
        return 1

    check_events_zone()
    check_base_zone()
    check_components_zone()
    check_utils_zone()

    if ERRORS:
        for line in ERRORS:
            print(f"check_core_frontend_canon: {line}", file=sys.stderr)
        print(f"check_core_frontend_canon: FAIL ({len(ERRORS)} issue(s))", file=sys.stderr)
        return 1
    print("check_core_frontend_canon: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
