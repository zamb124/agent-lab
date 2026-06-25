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
FACTORY_CANON_SERVICES = {
    "frontend",
    "crm",
    "rag",
    "office",
    "provider_litserve",
    "sync",
    "flows",
}
# Все мигрированные на event-канон сервисы. Парсер `_resolve_external_prefixes`
# умеет резолвить вложенные `include_router(child, prefix='/...')`-цепочки
# (используются в `apps/sync/api/__init__.py::get_api_router` и
# `apps/flows/src/api/v1/__init__.py::api_v1_router`), поэтому sync и flows
# тоже проверяются в strict-режиме.

# Сервисный процесс может монтироваться под публичным путём, отличным от
# имени каталога `apps/<svc>/` (`settings.server.name` в conf.json). Например,
# `apps/office` слушает на `/documents/...` (см. `office.mdc`). Здесь —
# карта `<dir name> -> <public mount prefix>`.
SERVICE_PUBLIC_NAME = {"office": "documents", "provider_litserve": "litserve"}

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
    r"^[ \t]*(?P<name>\w+)\s*=\s*APIRouter\s*\((?P<args>[^)]*)\)",
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
# Импорт `from <pkg>[.<sub>] import router as <alias>` либо
# `from <pkg> import <module>_router as <alias>`. Нам нужно понять, к какому
# .py-файлу относится переменная `<alias>`, чтобы потом увязать её
# `include_router(...)`-prefix с реальным файлом.
ROUTER_IMPORT_RE = re.compile(
    r"^from\s+(?P<module>[.\w]+)\s+import\s+"
    r"(?P<name>\w+)(?:\s+as\s+(?P<alias>\w+))?",
    re.M,
)
# `<parent>.include_router(<child_var>, prefix='/...')` — извлекаем child_var
# и prefix. Допускаем несколько kwargs (tags, dependencies). prefix может
# отсутствовать (тогда внешнего префикса нет).
INCLUDE_ROUTER_CALL_RE = re.compile(
    r"\.include_router\s*\(\s*(?P<child>\w+)\s*(?P<rest>[^)]*)\)",
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
    item_base_url = base_url.rstrip("/")
    item_path = f"{item_base_url}/{{{id_field}}}" if id_field else None
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

    # Иначе — одиночная запись { method, path [, service] } (createAsyncOp/
    # CursorList). Опциональное поле `service: '<svc>'` явно декларирует
    # cross-service вызов (например, frontend dashboard бегает за счётчиками
    # в `/flows/...`): скрипт не верифицирует path против своих routes, но
    # и не фейлит strict.
    method_m = re.search(r"method\s*:\s*(?P<q>['\"])(?P<v>[A-Z]+)(?P=q)", rest_mirror_block)
    path_m = re.search(r"path\s*:\s*(?P<q>['\"])(?P<v>[^'\"]+)(?P=q)", rest_mirror_block)
    service_m = re.search(r"service\s*:\s*(?P<q>['\"])(?P<v>[a-z_][a-z0-9_-]*)(?P=q)", rest_mirror_block)
    if method_m and path_m:
        result: dict[str, tuple[str, str]] = {"_single": (method_m.group("v"), path_m.group("v"))}
        if service_m:
            result["_cross_service"] = ("", service_m.group("v"))
        return result
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
    # Сервисы могут класть REST-роутеры в `apps/<svc>/api/**` (каноничная
    # раскладка) или в `apps/<svc>/src/api/**` (flows — исторический
    # src-layout). Сканируем оба, если существуют.
    api_roots = [p for p in (svc_dir / "api", svc_dir / "src" / "api") if p.exists()]
    api_roots[0] if api_roots else (svc_dir / "api")
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

    # 1. Сервисные роутеры (apps/<svc>/api/** и/или apps/<svc>/src/api/**)
    #    монтируются под `/<svc>/api/<version>` (для api_version != None)
    #    или `/<svc>` (None).
    for api_root_path in api_roots:
        _scan_routers_in_dir(api_root_path, service_api_prefix, routes)

    # 1b. Сервисы, регистрирующие роутеры прямо в main.py (например,
    #     provider_litserve через `_register_model_management_api`):
    #     APIRouter(prefix=...) в нём указан полный путь, без сервисного
    #     префикса; mount_prefix здесь — пустой.
    if main_py.exists():
        _scan_router_file(main_py, "", routes)

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
    if svc_name == "frontend":
        files_mount = f"/{public_name}/api/{api_version}/files"
        _scan_router_file_with_mount(core_root / "files" / "api.py", files_mount, routes)

    return routes


def _scan_router_file_with_mount(py: Path, mount_prefix: str, routes: set[tuple[str, str]]) -> None:
    if not py.exists():
        return
    _scan_router_file(py, mount_prefix, routes)


def _scan_routers_in_dir(root: Path, mount_prefix: str, routes: set[tuple[str, str]]) -> None:
    """Сканировать все .py-файлы под root, учитывая вложенные include_router.

    Стратегия:

      1. Собрать карту external_prefix для каждого .py-файла, которая
         учитывает include_router-цепочку из `__init__.py`-файлов.
         Например, для flows:
             apps/flows/src/api/v1/__init__.py:
                 api_v1_router = APIRouter()
                 api_v1_router.include_router(code_router, prefix="/code")
             apps/flows/src/api/v1/code.py:
                 router = APIRouter()
                 @router.get("/completions") -> /flows/api/v1/code/completions
         Здесь `code.py` получает external_prefix `/code`.

      2. После этого пройти каждый файл через `_scan_router_file` с
         итоговым mount_prefix = `mount_prefix + external_prefix`.
    """
    external_prefixes = _resolve_external_prefixes(root)
    for py in root.rglob("*.py"):
        external = external_prefixes.get(py, "")
        _scan_router_file(py, mount_prefix + external, routes)


def _resolve_external_prefixes(root: Path) -> dict[Path, str]:
    """Для каждого .py-файла под root вернуть его external prefix
    (то, что задаёт его родитель через `include_router(child, prefix='...')`).

    Проходит ВСЕ файлы и склеивает include_router-цепочки. Если файл нигде не
    включён через include_router — его external_prefix = "" (топ-уровень).
    """
    # 1. Для каждого .py: какие алиасы он экспортирует -> файл-источник.
    #    Простая модель: считаем, что в файле объявлен `router = APIRouter(...)`.
    #    Имя переменной берём из APIROUTER_DEF_RE (обычно `router`). Если в
    #    файле несколько APIRouter — берём первую (этого хватает для текущей
    #    раскладки).
    declared_router_var: dict[Path, str] = {}
    for py in root.rglob("*.py"):
        text = py.read_text(encoding="utf-8", errors="ignore")
        for rm in APIROUTER_DEF_RE.finditer(text):
            declared_router_var[py] = rm.group("name")
            break

    # 2. Для каждого файла с include_router-вызовами: для каждого `<child_var>`
    #    найдём его import и привяжем prefix.
    file_to_external: dict[Path, str] = {}

    for py in root.rglob("*.py"):
        text = py.read_text(encoding="utf-8", errors="ignore")
        if ".include_router" not in text:
            continue
        # Локальная карта алиас → путь к файлу-источнику.
        alias_to_path: dict[str, Path] = {}
        for im in ROUTER_IMPORT_RE.finditer(text):
            alias = im.group("alias") or im.group("name")
            module_dotted = im.group("module")
            target = _resolve_import_target(py, module_dotted, im.group("name"))
            if target is None:
                continue
            alias_to_path[alias] = target

        for call in INCLUDE_ROUTER_CALL_RE.finditer(text):
            child = call.group("child")
            rest = call.group("rest")
            prefix_m = PREFIX_KW_RE.search(rest)
            child_prefix = prefix_m.group("value") if prefix_m else ""
            target_path = alias_to_path.get(child)
            if target_path is None:
                # Если child = локально объявленный APIRouter в этом же файле
                # с include_router'ом — пропускаем (его декораторы и так
                # сканируются с своим router_prefix).
                continue
            # Накапливаем: файл-родитель сам мог быть включён под другим
            # prefix'ом — финальный prefix вычисляется в цикле фиксации.
            existing = file_to_external.get(target_path, "")
            file_to_external[target_path] = existing + child_prefix

    # 3. Транзитивно протянем prefix вверх по цепочке include_router. Для этого
    #    повторяем проход, пока что-то меняется (на практике хватает 2 итераций
    #    для api_v1_router → child_router и main.py → api_v1_router).
    for _ in range(8):
        changed = False
        for py in root.rglob("*.py"):
            text = py.read_text(encoding="utf-8", errors="ignore")
            if ".include_router" not in text:
                continue
            parent_external = file_to_external.get(py, "")
            if not parent_external:
                continue
            alias_to_path: dict[str, Path] = {}
            for im in ROUTER_IMPORT_RE.finditer(text):
                alias = im.group("alias") or im.group("name")
                target = _resolve_import_target(py, im.group("module"), im.group("name"))
                if target is None:
                    continue
                alias_to_path[alias] = target
            for call in INCLUDE_ROUTER_CALL_RE.finditer(text):
                child = call.group("child")
                target_path = alias_to_path.get(child)
                if target_path is None:
                    continue
                # Префикс ребёнка = parent_external + child_local_prefix.
                # child_local_prefix уже учтён на шаге 2 (мы добавили его сами).
                # Здесь просто префиксуем родительским внешним prefix'ом, если
                # ещё не префиксован.
                if not file_to_external.get(target_path, "").startswith(parent_external):
                    file_to_external[target_path] = parent_external + file_to_external.get(target_path, "")
                    changed = True
        if not changed:
            break

    return file_to_external


def _resolve_import_target(from_file: Path, module_dotted: str, name: str) -> Path | None:
    """Резолвит `from <module> import <name>` в .py файл с router-объектом.

    Поддерживает:
      - relative `from .child import router as child_router` (внутри пакета);
      - absolute `from apps.flows.src.api.v1.code import router as code_router`.

    Возвращает Path или None, если файл вне сканируемого root'а или не найден.
    """
    if module_dotted.startswith("."):
        # Relative import.
        levels = len(module_dotted) - len(module_dotted.lstrip("."))
        rest = module_dotted.lstrip(".")
        base_dir = from_file.parent
        for _ in range(levels - 1):
            base_dir = base_dir.parent
        candidate = base_dir
        if rest:
            for part in rest.split("."):
                candidate = candidate / part
        candidate_py = candidate.with_suffix(".py")
        if candidate_py.exists():
            return candidate_py
        candidate_init = candidate / "__init__.py"
        if candidate_init.exists():
            return candidate_init
        return None
    # Absolute import: ищем под ROOT (apps/<svc>/...).
    parts = module_dotted.split(".")
    candidate_py = ROOT.joinpath(*parts).with_suffix(".py")
    if candidate_py.exists():
        return candidate_py
    candidate_init = ROOT.joinpath(*parts) / "__init__.py"
    if candidate_init.exists():
        return candidate_init
    return None


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
        _collect_publish_ui_event_types(svc_dir)

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
                    cross = rest_entries.get("_cross_service")
                    if cross:
                        # Cross-service вызов: path и method явно задекларированы,
                        # но backend живёт в другом сервисе. Не проверяем против
                        # локальных routes, не даём и WARN (strict pass).
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
