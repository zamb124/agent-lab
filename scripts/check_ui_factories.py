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

Скрипт парсит JS как текст: AST не строим, обходим по регуляркам и читаем
плоские словари. Для динамических значений (`name: SOMETHING`,
`baseUrl: getUrl()`) выводим warning и пропускаем — статический lint не
претендует на полное покрытие.

Запуск:
    uv run python scripts/check_ui_factories.py [--app <svc>] [--strict]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APPS = ROOT / "apps"
I18N = ROOT / "core" / "i18n" / "translations"

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
        rec: dict = {
            "kind": match.group("kind"),
            "line": line_no,
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
        for path in ui_root.rglob("*.js"):
            text = path.read_text(encoding="utf-8")
            if any(kind + "(" in text for kind in FACTORY_KINDS):
                targets.append(path)

    i18n_index = _load_i18n_index()
    by_locale_ns: dict[str, dict[str, set[str]]] = {}
    for (locale, ns), keys in i18n_index.items():
        by_locale_ns.setdefault(ns, {})[locale] = keys

    errors: list[str] = []
    warnings: list[str] = []
    seen_names: dict[str, Path] = {}
    factories_total = 0

    for path in targets:
        rel = path.relative_to(ROOT)
        svc_name = path.relative_to(APPS).parts[0]
        for rec in _parse_factories(path):
            factories_total += 1
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
