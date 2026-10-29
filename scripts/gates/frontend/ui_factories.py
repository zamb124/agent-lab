#!/usr/bin/env python3
"""
Lint UI-фабрик (createAsyncOp / createResourceCollection / createCursorList /
createFacets / createForm) во всех `apps/<svc>/ui/events/resources/**/*.js`.

Проверки:
  1. Уникальность поля `name` среди всех фабрик платформы (имя — глобальный
     ключ в `factory-registry`, дубль => регистрация затрёт первую).
  2. `name` имеет формат `<ui-domain>/<entity>`, где `<ui-domain>` совпадает
     с каталогом сервиса (`apps/<svc>/ui/...`) или с явным публичным доменом
     сервиса из `PUBLIC_FACTORY_DOMAIN_BY_SERVICE`.
  3. `baseUrl` начинается с `/` и содержит сервисный префикс
     (FastAPI: `/<svc>/api/...` или `/<svc>/api/v1/...`).
  4. Парность toast-i18n-ключей: каждое значение `successToastKey` /
     `errorToastKey` (вкл. `toastKeys.*` у resource-collection) присутствует
     в `core/i18n/translations/{ru,en}/<ns>.json`.
  5. `idField` присутствует, если `operations` включают `update` / `remove` /
     `get` (без идентификатора эти операции невозможны).
  6. Фабрика из `apps/<svc>/ui/events/**`, на которую ссылается
     `useOp`/`useResource`/`useForm`/`useCursorList`/`useFacets`/`useSlice`
     в UI сервиса, обязана быть в `static factories` соответствующего `*-app.ts`.
     Иначе модалка/страница падает в `getFactory: not registered`.

Скрипт парсит JS как текст: AST не строим, обходим по регуляркам и читаем
плоские словари. Для динамических значений (`name: SOMETHING`,
`baseUrl: getUrl()`) выводим warning и пропускаем — статический lint не
претендует на полное покрытие.

Запуск:
    uv run python -m scripts.gates.frontend.ui_factories [--app <svc>] [--strict]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from scripts.gates.kit import REPO_ROOT as ROOT

APPS = ROOT / "apps"
I18N = ROOT / "core" / "i18n" / "translations"
CORE_FACTORY_RESOURCES = ROOT / "core" / "frontend" / "static" / "lib" / "events" / "resources"
# Фабрики платформенного ядра (файлы) — владелец 'platform'.
CORE_PLATFORM_OWNER = "platform"

# Общие ресурсы владельцев доменов: файл `core/frontend/static/lib/events/resources/*.resource.ts`
# может содержать фабрики одного или нескольких владельцев; владелец каждой фабрики — префикс
# `name` ('<svc>/...'), и он обязан быть существующим сервисом `apps/<svc>`.

FACTORY_KINDS = (
    "createAsyncOp",
    "createResourceCollection",
    "createCursorList",
    "createFacets",
    "createForm",
    "createSlice",
)

PUBLIC_FACTORY_DOMAIN_BY_SERVICE = {
    # UI не должен тащить внутреннее имя сервиса provider_litserve. Внешний
    # продуктовый домен для реестра системных моделей — Humanitec Models.
    "provider_litserve": "humanitec_models",
}

# Для `createSlice` проверяется дополнительно наличие `extraInitial`
# (минимум один ключ) и `extraReducer` (обязателен). `transport` / `request`
# /  `restMirror` у slice-фабрик запрещены — у них нет транспорта.
SLICE_ONLY_FORBIDDEN_FIELDS = ("transport", "request", "restMirror", "wsTimeoutMs")

CALL_RE = re.compile(
    r"\b(?P<kind>" + "|".join(FACTORY_KINDS) + r")\s*\(\s*\{",
)
STR_FIELD_RE = re.compile(
    r"^\s*(?P<key>name|baseUrl|idField|successToastKey|errorToastKey)\s*:\s*"
    r"(?P<q>['\"])(?P<value>[^'\"]+)(?P=q)",
    re.M,
)
TOAST_BLOCK_RE = re.compile(r"toastKeys\s*:\s*\{", re.M)
TOAST_INNER_RE = re.compile(
    r"\b(create|update|remove|create_error|update_error|remove_error)\s*:\s*"
    r"(?P<q>['\"])(?P<value>[^'\"]+)(?P=q)",
    re.M,
)
OPERATIONS_RE = re.compile(r"operations\s*:\s*\[(?P<list>[^\]]+)\]", re.M)


def _balance_braces(text: str, start: int) -> int:
    """Найти конец блока, начинающегося с `{` (символ под индексом start-1)."""
    depth = 1
    i = start
    while i < len(text):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        elif c in ("'", '"', "`"):
            quote = c
            j = i + 1
            while j < len(text) and text[j] != quote:
                if text[j] == "\\":
                    j += 1
                j += 1
            i = j
        i += 1
    return -1


def _load_i18n_index() -> dict[tuple[str, str], set[str]]:
    """Возвращает {(locale, namespace): set(flat_keys)}.

    `flat_keys` — точечная нотация всех листьев JSON-бандла.
    """
    index: dict[tuple[str, str], set[str]] = {}
    if not I18N.exists():
        return index
    for locale_dir in I18N.iterdir():
        if not locale_dir.is_dir():
            continue
        locale = locale_dir.name
        for path in locale_dir.glob("*.json"):
            ns = path.stem
            with path.open(encoding="utf-8") as fh:
                data = json.load(fh)
            keys: set[str] = set()
            _flatten(data, "", keys)
            index[(locale, ns)] = keys
    return index


def _flatten(obj, prefix: str, out: set[str]) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            full = f"{prefix}.{key}" if prefix else key
            if isinstance(value, (dict, list)):
                _flatten(value, full, out)
            else:
                out.add(full)
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            _flatten(value, f"{prefix}.{idx}" if prefix else str(idx), out)


EXTRA_INITIAL_RE = re.compile(r"\bextraInitial\s*:\s*\{", re.M)
EXTRA_REDUCER_RE = re.compile(r"\bextraReducer\s*:\s*(?:function|\()", re.M)
EXPORT_IDENT_RE = re.compile(
    r"export\s+const\s+(?P<ident>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*$"
)
STATIC_FACTORIES_RE = re.compile(r"static\s+factories\s*=\s*\[")
USE_HELPER_RE = re.compile(
    r"""this\.use(?:Op|Resource|Form|CursorList|Facets|Slice)\(\s*['\"]([^'\"]+)['\"]"""
)


def _parse_factories(path: Path) -> list[dict]:
    """Возвращает список фабрик из файла с метаданными для lint.

    Каждая запись: {kind, name, baseUrl, idField, ops, toasts, has_extra_initial,
    has_extra_reducer, forbidden_fields: [str]}.
    """
    text = path.read_text(encoding="utf-8")
    factories: list[dict] = []
    for match in CALL_RE.finditer(text):
        end = _balance_braces(text, match.end())
        if end < 0:
            continue
        block = text[match.end(): end]
        line_no = text.count("\n", 0, match.start()) + 1
        prefix = text[: match.start()].rstrip()
        ident_match = EXPORT_IDENT_RE.search(prefix[-200:])
        rec: dict = {
            "kind": match.group("kind"),
            "line": line_no,
            "ident": ident_match.group("ident") if ident_match else None,
            "name": None,
            "baseUrl": None,
            "idField": None,
            "ops": [],
            "toasts": [],
            "has_extra_initial": False,
            "has_extra_reducer": False,
            "forbidden_fields": [],
        }
        for inner in STR_FIELD_RE.finditer(block):
            key, value = inner.group("key"), inner.group("value")
            if key in ("successToastKey", "errorToastKey"):
                rec["toasts"].append(value)
            else:
                rec[key] = value
        for tblock in TOAST_BLOCK_RE.finditer(block):
            tend = _balance_braces(block, tblock.end())
            if tend < 0:
                continue
            for inner in TOAST_INNER_RE.finditer(block[tblock.end(): tend]):
                rec["toasts"].append(inner.group("value"))
        ops_match = OPERATIONS_RE.search(block)
        if ops_match:
            ops_raw = ops_match.group("list")
            rec["ops"] = [
                tok.strip().strip("'\"")
                for tok in ops_raw.split(",")
                if tok.strip().strip("'\"")
            ]
        if EXTRA_INITIAL_RE.search(block):
            rec["has_extra_initial"] = True
        if EXTRA_REDUCER_RE.search(block):
            rec["has_extra_reducer"] = True
        for forbidden in SLICE_ONLY_FORBIDDEN_FIELDS:
            if re.search(rf"\b{re.escape(forbidden)}\s*:", block):
                rec["forbidden_fields"].append(forbidden)
        factories.append(rec)
    return factories


def _parse_static_factory_idents(app_path: Path) -> set[str] | None:
    """Идентификаторы из `static factories = [...]`. Нет массива — None."""
    text = app_path.read_text(encoding="utf-8")
    match = STATIC_FACTORIES_RE.search(text)
    if not match:
        return None
    start = match.end() - 1
    depth = 0
    end = -1
    i = start
    while i < len(text):
        char = text[i]
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                end = i
                break
        elif char in ("'", '"', "`"):
            quote = char
            i += 1
            while i < len(text) and text[i] != quote:
                if text[i] == "\\":
                    i += 1
                i += 1
        i += 1
    if end < 0:
        return None
    block = text[start + 1 : end]
    block = re.sub(r"/\*.*?\*/", "", block, flags=re.S)
    block = re.sub(r"//[^\n]*", "", block)
    return set(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", block))


def _collect_used_factory_names(svc_ui: Path) -> set[str]:
    names: set[str] = set()
    for folder in ("pages", "modals", "components", "app"):
        root = svc_ui / folder
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.ts")):
            names.update(USE_HELPER_RE.findall(path.read_text(encoding="utf-8")))
    return names


def _check_app_registration(
    svc_name: str,
    svc_dir: Path,
    factories: list[dict],
    errors: list[str],
) -> None:
    app_dir = svc_dir / "ui" / "app"
    if not app_dir.exists():
        return
    app_files = sorted(app_dir.glob("*-app.ts"))
    if not app_files:
        return
    app_path = app_files[0]
    registered = _parse_static_factory_idents(app_path)
    if registered is None:
        return
    app_rel = app_path.relative_to(ROOT)
    name_to_rec: dict[str, dict] = {}
    for rec in factories:
        ident = rec.get("ident")
        name = rec.get("name")
        if ident and name:
            name_to_rec[name] = rec
    used_names = _collect_used_factory_names(svc_dir / "ui")
    for used in sorted(used_names):
        rec = name_to_rec.get(used)
        if rec is None:
            continue
        ident = rec["ident"]
        if ident not in registered:
            errors.append(
                f"{rec['path']}:{rec['line']}: фабрика {ident} "
                f"(name '{used}') используется в UI, но нет в static factories {app_rel}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", help="ограничить одним сервисом (frontend/sync/...)")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="ненулевой код возврата при warnings (по умолчанию — только при errors)",
    )
    args = parser.parse_args()

    targets: list[Path] = []
    services_root = sorted(p for p in APPS.iterdir() if p.is_dir())
    for svc_dir in services_root:
        if args.app and svc_dir.name != args.app:
            continue
        ui_root = svc_dir / "ui" / "events"
        if not ui_root.exists():
            continue
        for path in sorted(ui_root.rglob("*.ts")):
            text = path.read_text(encoding="utf-8")
            if any(kind + "(" in text for kind in FACTORY_KINDS):
                targets.append(path)

    if CORE_FACTORY_RESOURCES.exists():
        for core_path in sorted(CORE_FACTORY_RESOURCES.glob("*.resource.ts")):
            targets.append(core_path)

    i18n_index = _load_i18n_index()
    by_locale_ns: dict[str, dict[str, set[str]]] = {}
    for (locale, ns), keys in i18n_index.items():
        by_locale_ns.setdefault(ns, {})[locale] = keys

    errors: list[str] = []
    warnings: list[str] = []
    seen_names: dict[str, Path] = {}
    factories_total = 0
    factories_by_svc: dict[str, list[dict]] = defaultdict(list)

    for path in targets:
        rel = path.relative_to(ROOT)
        is_core_resource = path.is_relative_to(CORE_FACTORY_RESOURCES)
        file_svc_name = "" if is_core_resource else path.relative_to(APPS).parts[0]
        for rec in _parse_factories(path):
            factories_total += 1
            svc_name = file_svc_name
            if is_core_resource:
                owner_part = (rec["name"] or "").partition("/")[0]
                if owner_part != CORE_PLATFORM_OWNER and not (APPS / owner_part).is_dir():
                    errors.append(
                        f"{rel}:{rec['line']} {rec['kind']}: владелец '{owner_part}' из name "
                        f"'{rec['name']}' не является сервисом apps/<svc>"
                    )
                    continue
                svc_name = owner_part
            if args.app and args.app != svc_name:
                continue
            rec["path"] = rel
            if not is_core_resource:
                # Регистрацию в `static factories` проверяем только для локальных
                # фабрик сервиса: общие ресурсы core регистрирует PlatformApp или
                # каждый потребитель явно.
                factories_by_svc[svc_name].append(rec)
            kind = rec["kind"]
            name = rec["name"]
            line = rec["line"]
            prefix = f"{rel}:{line} {kind}"

            if not name:
                warnings.append(f"{prefix}: динамическое поле `name` — пропущено")
                continue

            if name in seen_names:
                errors.append(
                    f"{prefix}: дубликат name '{name}' "
                    f"(уже зарегистрирован в {seen_names[name]})"
                )
            else:
                seen_names[name] = rel

            if "/" not in name:
                errors.append(
                    f"{prefix}: name '{name}' должен иметь формат '<svc>/<entity>'"
                )
            else:
                svc_part, _, _ = name.partition("/")
                expected_svc_part = PUBLIC_FACTORY_DOMAIN_BY_SERVICE.get(svc_name, svc_name)
                if svc_part != expected_svc_part:
                    errors.append(
                        f"{prefix}: name '{name}' начинается с '{svc_part}/', "
                        f"ожидается '{expected_svc_part}/'"
                    )

            base_url = rec["baseUrl"]
            if base_url is not None:
                if not base_url.startswith("/"):
                    errors.append(
                        f"{prefix}: baseUrl '{base_url}' должен начинаться с '/'"
                    )
                else:
                    expected = f"/{svc_name}/api"
                    # Сервисные процессы могут монтироваться под публичным
                    # путём, отличным от имени каталога `apps/<svc>/`:
                    #   - `apps/office`  -> `/documents/...` (см. office.mdc).
                    #   - `apps/provider_litserve` -> `/litserve/...`
                    #     (короткое имя для UI/REST, см. main.py UI_PREFIX).
                    if svc_name == "office":
                        extra_allowed = ("/documents/api",)
                    elif svc_name == "provider_litserve":
                        extra_allowed = ("/litserve/api",)
                    else:
                        extra_allowed = ()
                    if not (
                        base_url.startswith(expected)
                        or base_url.startswith("/api/")
                        or any(base_url.startswith(p) for p in extra_allowed)
                    ):
                        warnings.append(
                            f"{prefix}: baseUrl '{base_url}' вне префикса '{expected}'"
                        )

            ops = set(rec["ops"])
            needs_id = ops & {"update", "remove", "get"}
            if kind == "createResourceCollection" and needs_id and not rec["idField"]:
                errors.append(
                    f"{prefix}: operations={sorted(needs_id)} требуют поле idField"
                )

            if kind == "createSlice":
                if not rec["has_extra_initial"]:
                    errors.append(
                        f"{prefix}: createSlice требует extraInitial "
                        f"(минимум один ключ, задающий каноничную форму slice)"
                    )
                if not rec["has_extra_reducer"]:
                    errors.append(
                        f"{prefix}: createSlice требует extraReducer (pure reducer)"
                    )
                if rec["forbidden_fields"]:
                    errors.append(
                        f"{prefix}: createSlice не поддерживает "
                        f"{rec['forbidden_fields']} — у slice нет транспорта"
                    )

            for toast_key in rec["toasts"]:
                if ":" not in toast_key:
                    errors.append(
                        f"{prefix}: toast-ключ '{toast_key}' без namespace "
                        f"(ожидается '<ns>:path.to.key')"
                    )
                    continue
                ns, dotted = toast_key.split(":", 1)
                ns_data = by_locale_ns.get(ns)
                if not ns_data:
                    errors.append(
                        f"{prefix}: namespace '{ns}' для toast-ключа '{toast_key}' не найден"
                    )
                    continue
                for locale in ("ru", "en"):
                    keys = ns_data.get(locale)
                    if keys is None:
                        errors.append(
                            f"{prefix}: бандл '{locale}/{ns}.json' отсутствует"
                        )
                    elif dotted not in keys:
                        errors.append(
                            f"{prefix}: toast-ключ '{toast_key}' нет в '{locale}/{ns}.json'"
                        )

    for svc_name, svc_factories in factories_by_svc.items():
        _check_app_registration(svc_name, APPS / svc_name, svc_factories, errors)

    print(
        f"check_ui_factories: фабрик найдено {factories_total} в {len(targets)} файлах"
    )
    for warn in warnings:
        print(f"WARN  {warn}")
    for err in errors:
        print(f"ERROR {err}")
    if errors:
        return 1
    if warnings and args.strict:
        return 2
    print("check_ui_factories: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
