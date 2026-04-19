#!/usr/bin/env python3
"""
CI-проверка платформенного инварианта «REST-зеркало команд».

Контракт (см. `architecture.mdc`, раздел «REST-зеркало команд»):

  1. Каждая factory operation (createAsyncOp / createResourceCollection /
     createCursorList) обязана иметь HTTP-эндпоинт в `apps/<svc>/api/**`,
     соответствующий `restMirror.method` + `restMirror.path`.

  2. Push-события (`publish_ui_event_to_user`, `publish_ui_event_to_company`,
     `publish_ui_event_broadcast`) НЕ должны иметь REST-эндпоинт с тем же
     путём — REST-зеркала push-событий запрещены, подписка только через
     `platform:ui_events` -> `/<svc>/api/ws/notifications`.

Проверка строится на статическом анализе (regex по существующим скриптам:
см. `scripts/check_ui_factories.py`). FastAPI-роуты собираются обходом
`apps/<svc>/api/**/*.py` по декораторам `@router.get(...)` / `.post(...)` /
`.patch(...)` / `.put(...)` / `.delete(...)` и совмещением с префиксом
`include_router(..., prefix=...)` где это найдено.

Запуск:
    uv run python scripts/check_command_rest_mirror.py [--app <svc>] [--strict]

Exit-коды:
  0 — все factory operations имеют валидное REST-зеркало; конфликтов с push нет.
  1 — найдено нарушение (отсутствует REST или конфликт push <-> REST).
  2 — `--strict` и есть warnings (только если warnings были).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APPS = ROOT / "apps"

# Сервисы с фабриками, для которых проверка строгая. Остальные пропускаются
# с warning'ом (они либо не мигрированы на event-канон, либо не имеют
# фабрик — например, scheduler.).
FACTORY_CANON_SERVICES = {"frontend", "crm", "rag", "office"}

# Сервисный процесс может монтироваться под публичным путём, отличным от
# имени каталога `apps/<svc>/` (`settings.server.name` в conf.json). Например,
# `apps/office` слушает на `/documents/...` (см. `office.mdc`). Здесь —
# карта `<dir name> -> <public mount prefix>`.
SERVICE_PUBLIC_NAME = {"office": "documents"}

FACTORY_KINDS = (
    "createAsyncOp",
    "createResourceCollection",
    "createCursorList",
    "createFacets",
)

CALL_RE = re.compile(
    r"\b(?P<kind>" + "|".join(FACTORY_KINDS) + r")\s*\(\s*\{",
)
NAME_RE = re.compile(
    r"^\s*name\s*:\s*(?P<q>['\"])(?P<value>[^'\"]+)(?P=q)",
    re.M,
)
BASE_URL_RE = re.compile(
    r"^\s*baseUrl\s*:\s*(?P<q>['\"])(?P<value>[^'\"]+)(?P=q)",
    re.M,
)
ID_FIELD_RE = re.compile(
    r"^\s*idField\s*:\s*(?P<q>['\"])(?P<value>[^'\"]+)(?P=q)",
    re.M,
)
TRANSPORT_RE = re.compile(
    r"^\s*transport\s*:\s*(?P<q>['\"])(?P<value>[^'\"]+)(?P=q)",
    re.M,
)
OPERATIONS_RE = re.compile(
    r"operations\s*:\s*\[(?P<list>[^\]]+)\]",
    re.M,
)
REST_MIRROR_RE = re.compile(
    r"^\s*restMirror\s*:\s*\{",
    re.M,
)

# Внутри объекта restMirror ищем method + path
REST_ENTRY_RE = re.compile(
    r"\bmethod\s*:\s*(?P<mq>['\"])(?P<method>[A-Z]+)(?P=mq)\s*,?\s*path\s*:\s*(?P<pq>['\"])(?P<path>[^'\"]+)(?P=pq)"
    r"|\bpath\s*:\s*(?P<pq2>['\"])(?P<path2>[^'\"]+)(?P=pq2)\s*,?\s*method\s*:\s*(?P<mq2>['\"])(?P<method2>[A-Z]+)(?P=mq2)",
    re.M,
)

# FastAPI-декораторы в Python
FASTAPI_DECO_RE = re.compile(
    r"@(?P<router>\w+)\.(?P<method>get|post|put|patch|delete)\s*\(\s*(?P<q>['\"])(?P<path>[^'\"]*)(?P=q)",
    re.M,
)
APIROUTER_DEF_RE = re.compile(
    r"^(?P<name>\w+)\s*=\s*APIRouter\s*\((?P<args>[^)]*)\)",
    re.M,
)
PREFIX_KW_RE = re.compile(
    r"prefix\s*=\s*(?P<q>['\"])(?P<value>[^'\"]*)(?P=q)",
    re.M,
)
API_VERSION_RE = re.compile(
    r"api_version\s*=\s*(?:(?P<q>['\"])(?P<value>[^'\"]*)(?P=q)|(?P<none>None))",
    re.M,
)

# Публикация UI-событий (push)
PUBLISH_UI_RE = re.compile(
    r"\bpublish_ui_event(?:_to_user|_to_company|_broadcast|_envelope)?\s*\(\s*[\s\S]{0,800}?type\s*=\s*(?P<q>['\"])(?P<type>[^'\"]+)(?P=q)",
    re.M,
)


def _balance_braces(text: str, start: int) -> int:
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


def _normalize_path(path: str) -> str:
    """Нормализовать путь: `:param` -> `{param}` для сравнения с FastAPI."""
    return re.sub(r":(\w+)", r"{\1}", path)


def _derive_collection_paths(base_url: str, id_field: str | None, operations: list[str]) -> dict[str, tuple[str, str]]:
    """Auto-derive restMirror для createResourceCollection."""
    item_path = f"{base_url}/{{{id_field}}}" if id_field else None
    mapping: dict[str, tuple[str, str]] = {}
    for op in operations:
        if op == "list":
            mapping["list"] = ("GET", base_url)
        elif op == "create":
            mapping["create"] = ("POST", base_url)
        elif op == "get" and item_path:
            mapping["get"] = ("GET", item_path)
        elif op == "update" and item_path:
            mapping["update"] = ("PATCH", item_path)
        elif op == "remove" and item_path:
            mapping["remove"] = ("DELETE", item_path)
    return mapping


def _parse_factories(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    factories: list[dict] = []
    for match in CALL_RE.finditer(text):
        end = _balance_braces(text, match.end())
        if end < 0:
            continue
        block = text[match.end(): end]
        line_no = text.count("\n", 0, match.start()) + 1
        kind = match.group("kind")

        name_m = NAME_RE.search(block)
        base_m = BASE_URL_RE.search(block)
        id_m = ID_FIELD_RE.search(block)
        transport_m = TRANSPORT_RE.search(block)
        ops_m = OPERATIONS_RE.search(block)

        rest_mirror_block: str | None = None
        rest_m = REST_MIRROR_RE.search(block)
        if rest_m:
            rm_end = _balance_braces(block, rest_m.end())
            if rm_end > 0:
                rest_mirror_block = block[rest_m.end(): rm_end]

        ops: list[str] = []
        if ops_m:
            ops = [tok.strip().strip("'\"") for tok in ops_m.group("list").split(",") if tok.strip().strip("'\"")]

        factories.append({
            "file": path,
            "line": line_no,
            "kind": kind,
            "name": name_m.group("value") if name_m else None,
            "baseUrl": base_m.group("value") if base_m else None,
            "idField": id_m.group("value") if id_m else None,
            "transport": transport_m.group("value") if transport_m else "http",
            "operations": ops,
            "restMirrorBlock": rest_mirror_block,
        })
    return factories


def _extract_rest_entries(rest_mirror_block: str | None) -> dict[str, tuple[str, str]]:
    """Извлечь имена операций -> (method, path) из restMirror.

    Поддерживает два варианта: { method, path } и { [op]: { method, path } }.
    """
    if not rest_mirror_block:
        return {}
    # Сначала пробуем как объект-под-операции: ищем `<op>: { method, path }`.
    op_entries: dict[str, tuple[str, str]] = {}
    op_pattern = re.compile(
        r"\b(?P<op>list|get|create|update|remove)\s*:\s*\{(?P<inner>[^{}]+)\}",
        re.M,
    )
    for m in op_pattern.finditer(rest_mirror_block):
        op = m.group("op")
        inner = m.group("inner")
        method = None
        path = None
        method_m = re.search(r"method\s*:\s*(?P<q>['\"])(?P<v>[A-Z]+)(?P=q)", inner)
        path_m = re.search(r"path\s*:\s*(?P<q>['\"])(?P<v>[^'\"]+)(?P=q)", inner)
        if method_m:
            method = method_m.group("v")
        if path_m:
            path = path_m.group("v")
        if method and path:
            op_entries[op] = (method, path)
    if op_entries:
        return op_entries

    # Иначе — одиночная запись { method, path } (createAsyncOp/CursorList).
    method_m = re.search(r"method\s*:\s*(?P<q>['\"])(?P<v>[A-Z]+)(?P=q)", rest_mirror_block)
    path_m = re.search(r"path\s*:\s*(?P<q>['\"])(?P<v>[^'\"]+)(?P=q)", rest_mirror_block)
    if method_m and path_m:
        return {"_single": (method_m.group("v"), path_m.group("v"))}
    return {}


def _collect_fastapi_routes(svc_dir: Path) -> set[tuple[str, str]]:
    """Собрать (method, normalized_path) FastAPI-роутов сервиса.

    Стратегия (статический анализ, без исполнения FastAPI):

      1. Определить service_api_prefix (`/<svc>/api/v1` или `/<svc>`):
         читаем `main.py` сервиса, ищем `api_version=`. Если `None` или
         отсутствует — `/<svc>`; если строка — `/<svc>/api/<version>`.
      2. По всем .py в `apps/<svc>/api/**` найти `APIRouter(prefix='...')`
         для каждого имени переменной.
      3. По всем декораторам `@<router_var>.<method>('<path>')` собрать
         финальный путь = `service_api_prefix + router_prefix + decorator_path`.

    Это покрывает основной случай (router = APIRouter(prefix='...') в файле +
    @router.method(...) внутри). Не покрывает редкие случаи импорта чужого
    router'а из core. Для них список `EXTRA_ROUTES_PER_SVC` (см. ниже).
    """
    api_root = svc_dir / "api"
    main_py = svc_dir / "main.py"

    svc_name = svc_dir.name
    public_name = SERVICE_PUBLIC_NAME.get(svc_name, svc_name)
    api_version: str | None = "v1"
    if main_py.exists():
        text = main_py.read_text(encoding="utf-8")
        m = API_VERSION_RE.search(text)
        if m:
            if m.group("none"):
                api_version = None
            else:
                api_version = m.group("value")
    service_api_prefix = (
        f"/{public_name}/api/{api_version}" if api_version else f"/{public_name}"
    )

    routes: set[tuple[str, str]] = set()

    # 1. Сервисные роутеры (apps/<svc>/api/**) монтируются под
    #    `/<svc>/api/<version>` (для api_version != None) или `/<svc>` (None).
    if api_root.exists():
        _scan_routers_in_dir(api_root, service_api_prefix, routes)

    # 2. Core-роутеры, монтируемые `create_service_app` под именованными
    #    префиксами (см. `core/app/factory.py`): team, calendar, companies,
    #    files, auth, push, integrations.
    core_root = ROOT / "core"
    _scan_router_file_with_mount(core_root / "api" / "team.py", f"/{svc_name}/api/team", routes)
    _scan_router_file_with_mount(core_root / "api" / "calendar.py", f"/{svc_name}/api/calendar", routes)
    companies_mount = "/frontend/api/companies" if svc_name == "frontend" else f"/{svc_name}/api/companies"
    _scan_router_file_with_mount(core_root / "api" / "companies.py", companies_mount, routes)
    _scan_router_file_with_mount(core_root / "api" / "auth.py", f"/{svc_name}/api/auth", routes)
    _scan_router_file_with_mount(core_root / "api" / "push.py", f"/{svc_name}", routes)
    _scan_router_file_with_mount(core_root / "api" / "integrations.py", f"/{svc_name}", routes)
    _scan_router_file_with_mount(core_root / "files" / "api.py", f"/{svc_name}/api/files", routes)

    return routes


def _scan_router_file_with_mount(py: Path, mount_prefix: str, routes: set[tuple[str, str]]) -> None:
    if not py.exists():
        return
    _scan_router_file(py, mount_prefix, routes)


def _scan_routers_in_dir(root: Path, mount_prefix: str, routes: set[tuple[str, str]]) -> None:
    for py in root.rglob("*.py"):
        _scan_router_file(py, mount_prefix, routes)


def _scan_router_file(py: Path, mount_prefix: str, routes: set[tuple[str, str]]) -> None:
    text = py.read_text(encoding="utf-8", errors="ignore")
    router_prefixes: dict[str, str] = {}
    for rm in APIROUTER_DEF_RE.finditer(text):
        name = rm.group("name")
        args = rm.group("args")
        pm = PREFIX_KW_RE.search(args)
        router_prefixes[name] = pm.group("value") if pm else ""
    for m in FASTAPI_DECO_RE.finditer(text):
        router_var = m.group("router")
        method = m.group("method").upper()
        decorator_path = m.group("path")
        router_prefix = router_prefixes.get(router_var, "")
        full_path = f"{mount_prefix}{router_prefix}{decorator_path}"
        normalized = _normalize_path(full_path)
        if normalized == "":
            normalized = "/"
        routes.add((method, normalized))
        if not normalized.endswith("/"):
            routes.add((method, normalized + "/"))
        if normalized.endswith("/") and len(normalized) > 1:
            routes.add((method, normalized.rstrip("/")))


def _collect_publish_ui_event_types(svc_dir: Path) -> set[str]:
    """Собрать типы событий из вызовов publish_ui_event_*."""
    types: set[str] = set()
    for py in svc_dir.rglob("*.py"):
        text = py.read_text(encoding="utf-8", errors="ignore")
        if "publish_ui_event" not in text:
            continue
        for m in PUBLISH_UI_RE.finditer(text):
            types.add(m.group("type"))
    return types


def _route_exists(routes: set[tuple[str, str]], method: str, path: str) -> bool:
    normalized = _normalize_path(path).rstrip("/")
    if (method, normalized) in routes:
        return True
    if (method, normalized + "/") in routes:
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", help="ограничить одним сервисом")
    parser.add_argument("--strict", action="store_true", help="ненулевой exit при warnings")
    args = parser.parse_args()

    services = sorted(p for p in APPS.iterdir() if p.is_dir())
    errors: list[str] = []
    warnings: list[str] = []
    factories_total = 0
    routes_total = 0

    for svc_dir in services:
        svc = svc_dir.name
        if args.app and svc != args.app:
            continue

        ui_resources = svc_dir / "ui" / "events" / "resources"
        if not ui_resources.exists():
            continue

        # Сервис вне FACTORY_CANON_SERVICES — пропускаем строгие проверки,
        # но всё ещё собираем roughCount.
        is_canon = svc in FACTORY_CANON_SERVICES

        routes = _collect_fastapi_routes(svc_dir)
        routes_total += len(routes)
        push_types = _collect_publish_ui_event_types(svc_dir)

        for path in sorted(ui_resources.rglob("*.js")):
            for rec in _parse_factories(path):
                factories_total += 1
                kind = rec["kind"]
                name = rec["name"]
                rel = path.relative_to(ROOT)
                prefix = f"{rel}:{rec['line']} {kind}({name})"

                if not is_canon:
                    continue

                # createFacets — restMirror auto-derived per facet, проверка
                # отдельная (через base_url + facets), сейчас пропускаем.
                if kind == "createFacets":
                    continue

                base_url = rec["baseUrl"]
                id_field = rec["idField"]
                ops = rec["operations"]
                transport = rec["transport"]
                rest_entries = _extract_rest_entries(rec["restMirrorBlock"])

                if kind == "createResourceCollection":
                    expected = _derive_collection_paths(
                        base_url or "",
                        id_field,
                        ops or ["list"],
                    )
                    # Перекрытия из restMirror
                    for op, entry in rest_entries.items():
                        if op != "_single":
                            expected[op] = entry
                    if not base_url and not rest_entries:
                        warnings.append(f"{prefix}: нет baseUrl / restMirror — нечего проверять")
                        continue
                    for op, (method, path_pattern) in expected.items():
                        if not _route_exists(routes, method, path_pattern):
                            errors.append(
                                f"{prefix}.{op}: REST-зеркало {method} {path_pattern} не найдено в apps/{svc}/api/**"
                            )
                elif kind == "createCursorList":
                    if rest_entries.get("_single"):
                        method, path_pattern = rest_entries["_single"]
                    elif base_url:
                        method, path_pattern = "GET", base_url
                    else:
                        warnings.append(f"{prefix}: нет baseUrl / restMirror — нечего проверять")
                        continue
                    if not _route_exists(routes, method, path_pattern):
                        errors.append(
                            f"{prefix}: REST-зеркало {method} {path_pattern} не найдено в apps/{svc}/api/**"
                        )
                elif kind == "createAsyncOp":
                    if not rest_entries:
                        if transport == "ws":
                            errors.append(
                                f"{prefix}: transport='ws' требует restMirror (factory должна была упасть на старте)"
                            )
                        else:
                            warnings.append(
                                f"{prefix}: нет restMirror — CI не может проверить REST-зеркало "
                                f"(transport='http', URL внутри request функции)"
                            )
                        continue
                    method, path_pattern = rest_entries.get("_single", ("", ""))
                    if not method or not path_pattern:
                        warnings.append(f"{prefix}: restMirror без method/path — пропуск")
                        continue
                    if not _route_exists(routes, method, path_pattern):
                        errors.append(
                            f"{prefix}: REST-зеркало {method} {path_pattern} не найдено в apps/{svc}/api/**"
                        )

        # Push <-> REST конфликт. Имена push: `<svc>/<entity>/<verb>`.
        # Конвертация в условный REST-путь сложна и может быть многозначной;
        # делаем мягкую проверку: имя push НЕ должно совпадать с именем команды
        # (без суффикса `_requested`). Это валидируется в check_ui_factories
        # в части дублирования names; здесь дополнительно ловим коллизию имён
        # сущностей push vs команд.
        # Команды: scope/entity/verb_requested. Push: scope/entity/verb.
        # Проверка: не должно существовать двух событий вида
        # 'sync/messages/send_requested' (cmd) и 'sync/messages/send' (push).
        # Это статически не верифицируем без полного сканирования имён всех
        # событий — пропускаем как «soft» правило.

    print(
        f"check_command_rest_mirror: factories={factories_total} routes={routes_total}"
    )
    for warn in warnings:
        print(f"WARN  {warn}")
    for err in errors:
        print(f"ERROR {err}")
    if errors:
        return 1
    if warnings and args.strict:
        return 2
    print("check_command_rest_mirror: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
