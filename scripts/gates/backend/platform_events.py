#!/usr/bin/env python3
"""CI gate: канон единой шины platform:events.

Проверки:
1. Нет legacy `platform:ui_events` / `core.ui_events` / `publish_ui_event`.
2. Нет HTTP wake/resume paths: internal/work-items/completed, internal/employee/inbox.
3. Нет прямого Redis XADD/PUBLISH на platform:events вне core/events/.
4. Publish-литералы имеют `register_platform_event`.
5. Запрет N× `publish_event_to_user` в for-цикле.
6. Orphan domain: register → publish + consumer
   (UI factory resources/lib OR flows durable path OR DOMAIN_FLOWS_ONLY_ALLOWLIST).
7. UI anti-pattern: page/modal/component domain push → HTTP _load/_reload (call-graph).
8. Naming bans: crm_ui_events, *_ws_broadcast, UIEvent envelope.
9. Docs: Pub/Sub UI / UIEvent as envelope.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from scripts.gates.kit import REPO_ROOT as ROOT

SCAN_DIRS = ("apps", "core", "tests", ".cursor/rules")
CODE_SCAN_DIRS = ("apps", "core", "tests", "scripts")
REGISTER_SCAN_DIRS = ("apps", "core")
SKIP_PARTS = {"node_modules", "__pycache__", ".git", "documentation-dist"}
TEXT_SUFFIXES = {".py", ".js", ".md", ".mdc", ".json", ".ts", ".tsx", ".yml", ".yaml"}
PY_SUFFIX = ".py"
# Сколько символов тела-выражения arrow-функции просматривать: тело без
# фигурных скобок не имеет однозначной границы без парсера JS.
EXPRESSION_BODY_WINDOW = 200
JS_SUFFIXES = {".js", ".ts"}

FORBIDDEN_SUBSTRINGS = (
    "platform:ui_events",
    "core.ui_events",
    "core/ui_events",
    "publish_ui_event",
)

FORBIDDEN_PATH_SUBSTRINGS = (
    "/internal/work-items/completed",
    "/internal/employee/inbox",
)

NAMING_BAN_SUBSTRINGS = (
    "crm_ui_events",
    "_ws_broadcast",
)

DOCS_FORBIDDEN = (
    "Pub/Sub UI",
)

TOAST_ONLY_ALLOWLIST: frozenset[str] = frozenset()

# Domain-only (delivery=None / flows triggers), без UI factory merge.
DOMAIN_FLOWS_ONLY_ALLOWLIST: frozenset[str] = frozenset(
    {
        "crm/entity/created",
        "crm/entity/updated",
        "crm/entity/deleted",
        "worktracker/work_item/assigned",
        # Леджер склада: факт проведённого движения — фильтры/триггеры
        # в flows (мувы не имеют своего list-ресурса, живут внутри накладной).
        "stock/move/done",
        # Мастер-карта каталога: durable consumer group `shop` пересобирает
        # снапшоты витрин; delivery=None — UI-пуша нет.
        "catalog/product/created",
        "catalog/product/updated",
        "catalog/product_overlay/changed",
    }
)

A2A_UI_EVENT_ALLOWLIST_FILES = frozenset(
    {
        "apps/flows/src/state/execution_state.py",
        "apps/flows/src/state/__init__.py",
        "core/a2a",
        "apps/flows/src/streaming/ui_events.py",
        "apps/flows/src/runtime_helpers/state_utils.py",
    }
)

STREAM_WRITE_RE = re.compile(
    r"""(?:\.xadd\s*\(\s*['\"]platform:events['\"]|"""
    r"""\.publish\s*\(\s*['\"]platform:events['\"]|"""
    r"""\.publish\s*\(\s*['\"]platform:ui_events['\"])""",
    re.M,
)

EVENT_TYPE_LIT_RE = re.compile(r"^[a-z][a-z0-9_]*(?:/[a-z0-9_]+){2,}$")
EVENT_TYPE_OCCURRENCE_RE = re.compile(
    r"['\"]([a-z][a-z0-9_]*(?:/[a-z0-9_]+){2,})['\"]"
)
CONST_ASSIGN_RE = re.compile(
    r'^([A-Z][A-Z0-9_]*)\s*=\s*[\'"]([^\'"]+)[\'"]\s*$',
    re.M,
)
REGISTER_CALL_RE = re.compile(
    r"register_platform_event\s*\(\s*(?:[\'\"]([^\'\"]+)[\'\"]|([A-Z][A-Z0-9_]*))",
)
PUBLISH_CALL_RE = re.compile(
    r"\b(?:publish_event(?:_to_user|_to_users|_to_company|_broadcast)?"
    r"|publish_domain_event|publish_realtime_events|publish_crm_entity_event"
    r"|publish_work_item_events|publish_crm_note_event|company_event)\s*\(",
)
IDENT_RE = re.compile(r"\b([A-Z][A-Z0-9_]*)\b")
FOR_USER_FANOUT_PUBLISH_RE = re.compile(
    r"for\s+(?P<var>\w+)\s+in\s+[^\n:]+:(?:[ \t]*(?:#.*)?\n)*"
    r"[ \t]*(?:await[ \t]+)?publish_event_to_user\s*\(\s*(?P=var)\b",
    re.M,
)
NOTIFY_PREFIX = "notify/"

USE_EVENT_STRING_RE = re.compile(
    r"this\.useEvent\s*\(\s*['\"]([a-z0-9_/]+)['\"]\s*,",
)
METHOD_DEF_RE = re.compile(
    r"(?:^|\n)[ \t]*(?:async[ \t]+)?(_[A-Za-z0-9]+)\s*\([^)]*\)\s*\{",
)
METHOD_CALL_RE = re.compile(r"\b(this\.)?(_(?:load|reload)[A-Za-z0-9]*|_load|_reload)\s*\(")
HTTPISH_IN_BODY_RE = re.compile(
    r"(?:\._load\b|\._reload\b|\.load\s*\(|\b_load[A-Za-z0-9]*\s*\(|\b_reload[A-Za-z0-9]*\s*\()"
)
# Только command-reply суффиксы фабрик; domain push `…/updated|created` НЕ сюда.
LOCAL_COMMAND_REPLY_RE = re.compile(
    r"/(?:succeeded|failed|loaded|list_loaded|item_removed)$"
)
UI_EVENT_IDENT_RE = re.compile(r"\bUIEvent\b")
PENDING_UI_EVENT_RE = re.compile(r"\bPendingUIEvent\b|ui_events_pending")

FLOWS_DURABLE_CONSUMER_SUFFIXES = (
    "apps/flows/src/services/platform_event_consumer.py",
    "apps/flows/src/triggers/handlers/platform_event.py",
)


def _iter_files(dirs: tuple[str, ...], suffixes: set[str]) -> list[Path]:
    files: list[Path] = []
    for dirname in dirs:
        root = ROOT / dirname
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            if path.suffix not in suffixes:
                continue
            files.append(path)
    return files


def _matching_paren_end(text: str, open_idx: int) -> int:
    depth = 0
    i = open_idx
    while i < len(text):
        ch = text[i]
        if ch in ("'", '"', "`"):
            quote = ch
            i += 1
            while i < len(text) and text[i] != quote:
                if text[i] == "\\":
                    i += 1
                i += 1
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _matching_brace_end(text: str, open_idx: int) -> int:
    depth = 0
    i = open_idx
    while i < len(text):
        ch = text[i]
        if ch in ("'", '"', "`"):
            quote = ch
            i += 1
            while i < len(text) and text[i] != quote:
                if text[i] == "\\":
                    i += 1
                i += 1
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _collect_const_event_types(py_files: list[Path]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for path in py_files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in CONST_ASSIGN_RE.finditer(text):
            name = match.group(1)
            value = match.group(2)
            if EVENT_TYPE_LIT_RE.match(value):
                mapping[name] = value
    return mapping


def _collect_registered_types(
    py_files: list[Path],
    const_map: dict[str, str],
) -> set[str]:
    registered: set[str] = set()
    for path in py_files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in REGISTER_CALL_RE.finditer(text):
            lit = match.group(1)
            name = match.group(2)
            if lit is not None:
                registered.add(lit)
            elif name is not None:
                resolved = const_map.get(name)
                if resolved is not None:
                    registered.add(resolved)
    return registered


def _collect_published_types(
    py_files: list[Path],
    const_map: dict[str, str],
) -> dict[str, list[str]]:
    published: dict[str, list[str]] = {}
    type_to_consts: dict[str, list[str]] = {}
    for const_name, event_type in const_map.items():
        type_to_consts.setdefault(event_type, []).append(const_name)

    for path in py_files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        found_types: set[str] = set()

        for match in PUBLISH_CALL_RE.finditer(text):
            open_paren = match.end() - 1
            close_paren = _matching_paren_end(text, open_paren)
            if close_paren < 0:
                continue
            body = text[open_paren + 1 : close_paren]
            for lit_match in EVENT_TYPE_OCCURRENCE_RE.finditer(body):
                found_types.add(lit_match.group(1))
            for ident_match in IDENT_RE.finditer(body):
                name = ident_match.group(1)
                resolved = const_map.get(name)
                if resolved is not None:
                    found_types.add(resolved)

        for lit_match in EVENT_TYPE_OCCURRENCE_RE.finditer(text):
            value = lit_match.group(1)
            start = lit_match.start()
            window = text[max(0, start - 40) : start]
            if "register_platform_event" in window:
                continue
            if re.search(r"\btype\s*=\s*$", window) or re.search(
                r"\bevent_type\s*=\s*$", window
            ):
                found_types.add(value)

        for event_type, const_names in type_to_consts.items():
            for const_name in const_names:
                if not re.search(rf"\b{const_name}\b", text):
                    continue
                if re.search(
                    rf"(?:publish_|broadcast_|publish_crm_entity_event|"
                    rf"publish_realtime_events|publish_work_item_events)"
                    rf".{{0,200}}\b{const_name}\b"
                    rf"|\b{const_name}\b.{{0,80}}"
                    rf"(?:publish_|broadcast_)",
                    text,
                    re.S,
                ):
                    found_types.add(event_type)
                if re.search(rf"publish_crm_entity_event\s*\(\s*{const_name}\b", text):
                    found_types.add(event_type)
                if re.search(
                    rf"(?:_publish|publish_event_to_users|publish_event_to_company|"
                    rf"publish_event_to_user|publish_domain_event)\s*\([^;]{{0,200}}\b{const_name}\b",
                    text,
                    re.S,
                ):
                    found_types.add(event_type)

        for event_type in found_types:
            if event_type.startswith(NOTIFY_PREFIX):
                continue
            if event_type.endswith("_requested"):
                continue
            if not EVENT_TYPE_LIT_RE.match(event_type):
                continue
            published.setdefault(event_type, []).append(rel)
    return published


def _is_ui_factory_resource_path(rel: str) -> bool:
    if "/ui/events/resources/" in rel:
        return True
    if rel.startswith("core/frontend/static/lib/events/"):
        return True
    return False


def _collect_ui_factory_consumed_types(js_files: list[Path]) -> set[str]:
    """Только factory resources / core event lib — не pages/modals."""
    consumed: set[str] = set()
    for path in js_files:
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if not _is_ui_factory_resource_path(rel):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in EVENT_TYPE_OCCURRENCE_RE.finditer(text):
            value = match.group(1)
            if EVENT_TYPE_LIT_RE.match(value):
                consumed.add(value)
    return consumed


def _collect_flows_durable_consumed_types(
    py_files: list[Path],
    const_map: dict[str, str],
) -> set[str]:
    consumed: set[str] = set()
    for path in py_files:
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if not any(rel.endswith(suffix) or rel == suffix for suffix in FLOWS_DURABLE_CONSUMER_SUFFIXES):
            # also allow exact relative match
            if rel not in FLOWS_DURABLE_CONSUMER_SUFFIXES and not any(
                rel.endswith(s.split("/")[-1]) and "platform_event" in rel for s in FLOWS_DURABLE_CONSUMER_SUFFIXES
            ):
                if rel not in (
                    "apps/flows/src/services/platform_event_consumer.py",
                    "apps/flows/src/triggers/handlers/platform_event.py",
                ):
                    continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in EVENT_TYPE_OCCURRENCE_RE.finditer(text):
            value = match.group(1)
            if EVENT_TYPE_LIT_RE.match(value):
                consumed.add(value)
        for const_name, event_type in const_map.items():
            if re.search(rf"\b{const_name}\b", text):
                consumed.add(event_type)
    return consumed


def _extract_method_bodies(text: str) -> dict[str, str]:
    bodies: dict[str, str] = {}
    for match in METHOD_DEF_RE.finditer(text):
        name = match.group(1)
        brace_open = text.find("{", match.end() - 1)
        if brace_open < 0:
            continue
        brace_close = _matching_brace_end(text, brace_open)
        if brace_close < 0:
            continue
        bodies[name] = text[brace_open : brace_close + 1]
    return bodies


def _handler_reaches_http(handler_src: str, method_bodies: dict[str, str]) -> bool:
    if HTTPISH_IN_BODY_RE.search(handler_src):
        return True
    visited: set[str] = set()
    stack: list[str] = []
    for call in METHOD_CALL_RE.finditer(handler_src):
        name = call.group(2)
        stack.append(name)
    # also this._foo() where _foo is any method that may load
    for call in re.finditer(r"this\.(_[A-Za-z0-9]+)\s*\(", handler_src):
        stack.append(call.group(1))
    while stack:
        name = stack.pop()
        if name in visited:
            continue
        visited.add(name)
        body = method_bodies.get(name)
        if body is None:
            if name.startswith("_load") or name.startswith("_reload"):
                return True
            continue
        if HTTPISH_IN_BODY_RE.search(body):
            return True
        for call in re.finditer(r"this\.(_[A-Za-z0-9]+)\s*\(", body):
            stack.append(call.group(1))
    return False


def _extract_arrow_or_fn_handler(text: str, use_event_match_end: int) -> str | None:
    """После `useEvent('type',` — тело arrow/function до закрытия useEvent(...)."""
    i = use_event_match_end
    while i < len(text) and text[i] in " \t\n\r":
        i += 1
    # skip optional async
    if text.startswith("async", i):
        i += 5
        while i < len(text) and text[i] in " \t\n\r":
            i += 1
    if text.startswith("(", i):
        close = _matching_paren_end(text, i)
        if close < 0:
            return None
        i = close + 1
        while i < len(text) and text[i] in " \t\n\r":
            i += 1
        if text.startswith("=>", i):
            i += 2
            while i < len(text) and text[i] in " \t\n\r":
                i += 1
            if i < len(text) and text[i] == "{":
                end = _matching_brace_end(text, i)
                if end < 0:
                    return None
                return text[i : end + 1]
            # Тело-выражение без фигурных скобок (`() => this._foo(...)`):
            # границу такого тела точно определяет только парсер JS, поэтому
            # берём окно фиксированной длины — проверкам канона хватает, так как
            # они ищут в теле обращения к фабрикам, а не разбирают его целиком.
            return text[i : i + EXPRESSION_BODY_WINDOW]
    if text.startswith("function", i):
        brace = text.find("{", i)
        if brace < 0:
            return None
        end = _matching_brace_end(text, brace)
        if end < 0:
            return None
        return text[brace : end + 1]
    return None


USE_EVENT_ANY_RE = re.compile(r"this\.useEvent\s*\(")
# Триггеры смены области данных: страница обязана перезагрузить другой набор.
SCOPE_CHANGE_EVENT_RE = re.compile(
    r"^(?:CoreEvents\.)?(?:UI_NAMESPACE_CHANGED|UI_[A-Z_]*RELOAD_REQUESTED|ROUTER_[A-Z_]+|I18N_[A-Z_]+"
    r"|THEME_[A-Z_]+|COMPANIES_[A-Z_]+|AUTH_USER_LOADED|AUTH_COMPANY_SWITCHED)$"
)
RELOAD_IN_HANDLER_RE = re.compile(
    r"(?:\.load\s*\(|(?<!location)\.reload\s*\(|\.loadMore\s*\(|\.dispatch\s*\(\s*[A-Za-z_.]*(?:LOAD_REQUESTED|LIST_REQUESTED)\b)"
)
RUN_TARGET_RE = re.compile(r"this\.(_[A-Za-z0-9]+)\.run\s*\(")
LOADER_METHOD_PREFIXES = ("_load", "_reload", "_refresh", "_fetch")
MUTATION_WORD_RE = re.compile(
    r"(create|update|remove|delete|merge|move|claim|complete|cancel|assign|upload|revoke|save|patch"
    r"|set|toggle|enable|disable|rebuild|restore|import|start|stop|apply|rotate|promote|bind|attach"
    r"|detach|reset|approve|decline|publish|archive|duplicate|copy|rename|send|resend|sync|generate"
    r"|analyze|format|repair|invite|accept|reject|join|leave|mark|pin|unpin|lock|unlock|review)",
    re.IGNORECASE,
)
READ_OUTCOME_EVENT_RE = re.compile(r"/(?:[a-z_]*loaded|[a-z_]*failed)$|[._][A-Z_]*(?:LOADED|FAILED)$")
COMMAND_OUTCOME_EVENT_RE = re.compile(
    r"(?:/(?:succeeded|failed|loaded|list_loaded|item_loaded|item_failed|item_removed)$"
    r"|\.events\.(?:SUCCEEDED|FAILED|LOADED|LIST_LOADED|ITEM_LOADED|ITEM_FAILED"
    r"|CREATED|UPDATED|REMOVED|CREATE_FAILED|UPDATE_FAILED|REMOVE_FAILED)$)"
)


def _is_read_outcome(type_label: str) -> bool:
    """Исход чтения (list/item/search/…): цепочка зависимых загрузок — не перезагрузка."""
    if READ_OUTCOME_EVENT_RE.search(type_label):
        return True
    if not COMMAND_OUTCOME_EVENT_RE.search(type_label):
        return False
    return MUTATION_WORD_RE.search(type_label) is None


def _push_reload_roots() -> list[Path]:
    roots: list[Path] = []
    for svc_dir in sorted((ROOT / "apps").iterdir()):
        ui_dir = svc_dir / "ui"
        if not ui_dir.is_dir():
            continue
        for kind in ("pages", "modals", "components"):
            if (ui_dir / kind).is_dir():
                roots.append(ui_dir / kind)
    roots.append(ROOT / "core" / "frontend" / "static" / "lib" / "components")
    return roots


def _use_event_type_label(type_src: str) -> str:
    stripped = type_src.strip()
    literal = re.fullmatch(r"['\"]([^'\"]+)['\"]", stripped)
    if literal:
        return literal.group(1)
    return stripped


def _handler_reaches_reload(handler_src: str, method_bodies: dict[str, str]) -> bool:
    """`.load()` — перезагрузка всегда; `.run()` — если цель читающий op; неизвестный `_load*()` — тоже."""

    def _hits(src: str) -> bool:
        if RELOAD_IN_HANDLER_RE.search(src):
            return True
        return any(MUTATION_WORD_RE.search(m.group(1)) is None for m in RUN_TARGET_RE.finditer(src))

    if _hits(handler_src):
        return True
    visited: set[str] = set()
    stack: list[str] = [m.group(1) for m in re.finditer(r"this\.(_[A-Za-z0-9]+)\s*\(", handler_src)]
    while stack:
        name = stack.pop()
        if name in visited:
            continue
        visited.add(name)
        body = method_bodies.get(name)
        if body is None:
            if name.startswith(LOADER_METHOD_PREFIXES):
                return True
            continue
        if _hits(body):
            return True
        stack.extend(m.group(1) for m in re.finditer(r"this\.(_[A-Za-z0-9]+)\s*\(", body))
    return False


def _check_push_reload(errors: list[str]) -> None:
    """Событие → перезагрузка запрещено: push и SUCCEEDED-исходы мержатся в фабрике.

    Ловит `this.useEvent(<type>, handler)` для push-типов, `CoreEvents.WS_CONNECTED` и исходов
    мутаций (`*_update/succeeded`, `.events.CREATED|UPDATED|REMOVED`, …), где handler доходит
    до `.load()/.reload()`, `.run()` читающего op или неизвестного `_load*()`. Исходы чтения
    (`/loaded`, `*_list/succeeded`, `*_bounds/succeeded`, …) — цепочка зависимых загрузок, не
    перезагрузка; `.run()` мутирующего op (`_namespaceUpdateOp.run`) — бизнес-цепочка.
    Исключение — смена области данных (`UI_NAMESPACE_CHANGED`, `*_RELOAD_REQUESTED`,
    `ROUTER_*`, `I18N_*`, `THEME_*`, `COMPANIES_*`, `AUTH_USER_LOADED`, `AUTH_COMPANY_SWITCHED`):
    другой пользователь/компания/пространство — другой набор данных, это новая загрузка.
    `WS_CONNECTED` сюда не входит: досинхронизацию после обрыва делает фабрика
    (`extraEffect` + `reloadLastList`/`rerunLastRequest`).
    """
    for root in _push_reload_roots():
        if not root.exists():
            continue
        for path in sorted(p for g in ("*.js", "*.ts") for p in root.rglob(g)):
            text = path.read_text(encoding="utf-8", errors="ignore")
            rel = str(path.relative_to(ROOT)).replace("\\", "/")
            method_bodies = _extract_method_bodies(text)
            for match in USE_EVENT_ANY_RE.finditer(text):
                open_paren = text.find("(", match.start())
                close_paren = _matching_paren_end(text, open_paren)
                if close_paren < 0:
                    continue
                call_src = text[open_paren + 1 : close_paren]
                first_comma = call_src.find(",")
                if first_comma < 0:
                    continue
                type_label = _use_event_type_label(call_src[:first_comma])
                if SCOPE_CHANGE_EVENT_RE.match(type_label):
                    continue
                if _is_read_outcome(type_label):
                    continue
                handler_src = call_src[first_comma + 1 :]
                if not _handler_reaches_reload(handler_src, method_bodies):
                    continue
                line = text.count("\n", 0, match.start()) + 1
                errors.append(
                    f"{rel}:{line}: useEvent({type_label}) → load/reload "
                    f"(merge in factory extraReducer)"
                )


def _is_a2a_allowlisted(rel: str) -> bool:
    if "ui_events_pending" in rel or "PendingUIEvent" in rel:
        return True
    for prefix in A2A_UI_EVENT_ALLOWLIST_FILES:
        if rel == prefix or rel.startswith(prefix.rstrip("/") + "/"):
            return True
    return False


def _check_naming_and_docs(errors: list[str]) -> None:
    for path in _iter_files(SCAN_DIRS, TEXT_SUFFIXES):
        text = path.read_text(encoding="utf-8", errors="ignore")
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if rel.startswith("apps/") or rel.startswith("core/"):
            for needle in NAMING_BAN_SUBSTRINGS:
                if needle in text:
                    if needle == "_ws_broadcast" and "test_crm_" in rel and "_broadcast" in rel:
                        continue
                    errors.append(f"{rel}: forbidden identifier substring {needle!r}")
            if UI_EVENT_IDENT_RE.search(text) and not PENDING_UI_EVENT_RE.search(text):
                if not _is_a2a_allowlisted(rel):
                    if "PendingUIEvent" in text or "ui_events_pending" in text:
                        pass
                    elif "≠" in text or "не platform" in text.lower():
                        pass
                    else:
                        errors.append(
                            f"{rel}: forbidden UIEvent as platform envelope "
                            f"(use PlatformEvent; A2A pending allowlist only)"
                        )
        if rel.startswith(".cursor/rules/"):
            for needle in DOCS_FORBIDDEN:
                if needle in text:
                    errors.append(f"{rel}: forbidden docs phrase {needle!r}")
            for m in re.finditer(r"\bUIEvent\b", text):
                window = text[max(0, m.start() - 40) : m.end() + 40]
                if "Не `UIEvent`" in window or "не `UIEvent`" in window:
                    continue
                if "Запрещены `UIEvent`" in window or "запрещены `UIEvent`" in window.lower():
                    continue
                if "PendingUIEvent" in window:
                    continue
                if "PlatformEvent" in window:
                    continue
                if "UIEventTarget" in window:
                    continue
                # Glossary ban column: `| Use X | UIEvent, ... |`
                if "|" in window and ("chat event" in window or "chat event" in text[m.start() : m.end() + 80]):
                    continue
                errors.append(f"{rel}: UIEvent used as platform envelope near {window!r}")
                break


def _check_bare_push_literals_outside_types(errors: list[str]) -> None:
    """A9: domain push string literals только в events/resources или events/types."""
    types_files = [p for g in ("*/ui/events/types.js", "*/ui/events/types.ts") for p in (ROOT / "apps").glob(g)]
    banned_literals: set[str] = set()
    for path in types_files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in EVENT_TYPE_OCCURRENCE_RE.finditer(text):
            banned_literals.add(match.group(1))
    if not banned_literals:
        return
    lit_re = re.compile(
        r"['\"]("
        + "|".join(re.escape(x) for x in sorted(banned_literals, key=len, reverse=True))
        + r")['\"]"
    )
    for svc_ui in (ROOT / "apps").glob("*/ui"):
        for kind in ("pages", "modals", "components", "app"):
            root = svc_ui / kind
            if not root.exists():
                continue
            for path in (p for g in ("*.js", "*.ts") for p in root.rglob(g)):
                rel = str(path.relative_to(ROOT)).replace("\\", "/")
                if "/events/resources/" in rel or "/events/types." in rel:
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
                for match in lit_re.finditer(text):
                    errors.append(
                        f"{rel}: bare push literal {match.group(1)!r} — "
                        f"import from ui/events/types.js"
                    )


def main() -> int:
    errors: list[str] = []
    for path in _iter_files(SCAN_DIRS, TEXT_SUFFIXES):
        text = path.read_text(encoding="utf-8", errors="ignore")
        rel = path.relative_to(ROOT)
        for needle in FORBIDDEN_SUBSTRINGS:
            if needle in text:
                errors.append(f"{rel}: forbidden substring {needle!r}")
        rel_s = str(rel).replace("\\", "/")
        if rel_s.split("/", 1)[0] in CODE_SCAN_DIRS:
            for needle in FORBIDDEN_PATH_SUBSTRINGS:
                if needle in text:
                    errors.append(f"{rel}: forbidden HTTP wake path {needle!r}")
        if "core/events" not in rel_s:
            if STREAM_WRITE_RE.search(text):
                errors.append(
                    f"{rel}: direct Redis write to platform event stream outside core/events"
                )

    py_files = _iter_files(REGISTER_SCAN_DIRS, {PY_SUFFIX})
    const_map = _collect_const_event_types(py_files)
    registered = _collect_registered_types(py_files, const_map)
    published = _collect_published_types(py_files, const_map)
    for event_type, locations in sorted(published.items()):
        if event_type not in registered:
            locs = ", ".join(sorted(set(locations))[:5])
            errors.append(
                f"unregistered publish type {event_type!r} "
                f"(no register_platform_event); sites: {locs}"
            )

    js_files = _iter_files(("apps", "core/frontend"), JS_SUFFIXES)
    ui_consumed = _collect_ui_factory_consumed_types(js_files)
    flows_consumed = _collect_flows_durable_consumed_types(py_files, const_map)
    for event_type in sorted(registered):
        if event_type.startswith(NOTIFY_PREFIX):
            continue
        if event_type not in published:
            errors.append(f"orphan register {event_type!r}: no publish call-site")
            continue
        if event_type in TOAST_ONLY_ALLOWLIST:
            continue
        if event_type in DOMAIN_FLOWS_ONLY_ALLOWLIST:
            continue
        if event_type in ui_consumed or event_type in flows_consumed:
            continue
        errors.append(
            f"orphan register {event_type!r}: published but no UI factory/flows consumer "
            f"(add factory merge or unregister)"
        )

    for path in py_files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        rel = path.relative_to(ROOT)
        if FOR_USER_FANOUT_PUBLISH_RE.search(text):
            errors.append(
                f"{rel}: for-loop publish_event_to_user fan-out "
                f"(use publish_event_to_users for one domain fact)"
            )

    _check_push_reload(errors)
    _check_bare_push_literals_outside_types(errors)
    _check_naming_and_docs(errors)

    if errors:
        print("check_platform_events_canon: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    print("check_platform_events_canon: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
