#!/usr/bin/env python3
"""
Cross-check ключей переводов: код ↔ JSON-бандлы.

Что делает:
  1. Сканирует JS (`apps/<svc>/ui/**/*.js` + `core/frontend/static/lib/**/*.js`)
     и собирает все вызовы `t('key', vars?, namespace?)` / `this.t('key', ...)`.
  2. Загружает все `core/i18n/translations/{ru,en}/*.json` (без префикса `_`),
     каждый файл = namespace в корневом бандле.
  3. Сообщает:
        --mode missing : ключи, которые код использует, но в бандле их нет.
        --mode unused  : ключи, которые лежат в бандле, но код их не дёргает
                         (динамика/toasts и др. — scripts/i18n_unused_scan_exclusions.py).
        --mode all     : и то, и другое (по умолчанию).
  4. Динамические ключи (`t(\\`prefix.${var}\\`)`, `t('a' + suffix)`) пропускаются
     и попадают в счётчик skipped — ручной ревью.

Резолв namespace для каждого использования (как в `translate()` runtime):
   1. Если 3-й аргумент задан как `I18nNs.X` или строковый литерал — берём его.
   2. Иначе — `static i18nNamespace = I18nNs.X` найденный в этом же файле.
   3. Иначе — дефолт сервиса по пути файла:
        apps/<svc>/ui/...      → svc           (если `<svc>.json` существует)
        core/frontend/static/lib/... → 'platform' (если `platform.json` существует)
   4. Иначе — без namespace (только прямой путь по корню бандла).

Поиск ключа в бандле (как в `translate()`):
   a) прямой путь от корня: bundle[seg0][seg1]...
   b) bundle[ns][seg0][seg1]...

Ключ считается найденным, если он резолвится хотя бы в одной локали (ru/en).
Unused считается отдельно по каждой локали (по объединению используемых ключей).

Запуск:
  uv run python scripts/check_i18n_keys.py            # all
  uv run python scripts/check_i18n_keys.py --mode missing
  uv run python scripts/check_i18n_keys.py --mode unused
  uv run python scripts/check_i18n_keys.py --strict   # exit 1 при находках
  uv run python scripts/check_i18n_keys.py --app frontend
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = Path(__file__).resolve().parent


def _unused_scan_excluded(fullkey: str) -> bool:
    import importlib.util

    name = "_i18n_unused_scan_exclusions"
    mod = sys.modules.get(name)
    if mod is None:
        path = _SCRIPTS / "i18n_unused_scan_exclusions.py"
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise RuntimeError("check_i18n_keys: cannot load i18n_unused_scan_exclusions.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return mod.terminal_key_excluded_from_unused_report(fullkey)


APPS = ROOT / "apps"
CORE_LIB = ROOT / "core" / "frontend" / "static" / "lib"
TRANSLATIONS = ROOT / "core" / "i18n" / "translations"
LOCALES = ("ru", "en")

# I18nNs.X → строка namespace. Должно совпадать с
# core/frontend/static/lib/utils/i18n-namespace.js.
I18N_NS_MAP = {
    "BILLING": "billing",
    "LANDING": "landing",
    "PLATFORM": "platform",
    "FRONTEND": "frontend",
    "FRONTEND_PRODUCTS": "frontend_products",
    "PRIVACY": "privacy",
    "TERMS": "terms",
    "COMMON": "common",
}

# Ключи в бандле, которые НЕ считаются unused (динамическая индексация).
# Если значение поля — список или объект, и весь подключ перебирается циклом
# (например `data.list.map(...)` → `t('section_X.list.0')`, `1`, ...) —
# рантайм всё равно достаёт это через t(), но статически мы видим только
# динамику. Поэтому не reportим как unused.
DYNAMIC_LIST_HINTS = ("list", "items", "options", "values")

CALL_RE = re.compile(
    r"""
    (?<![\w.])              # не часть длинного идентификатора, но this. перед t — ОК
    (?:this\.)?             # опционально this.
    t                       # имя метода
    \(                      # открывающая скобка
    \s*
    (['"`])                 # 1: тип кавычки
    ([\s\S]*?)              # 2: содержимое строки-ключа
    \1                      # закрытие тем же типом кавычки
    ([^)]*)                 # 3: остаток до ближайшей закрывающей скобки (наивно)
    \)
    """,
    re.VERBOSE,
)

CLASS_NS_RE = re.compile(
    r"static\s+i18nNamespace\s*=\s*(?:I18nNs\.([A-Z_]+)|['\"]([a-z][a-z0-9_]*)['\"])\s*;?"
)
NS_FROM_ARG_RE = re.compile(
    r"I18nNs\.([A-Z_]+)|['\"]([a-z][a-z0-9_]*)['\"]"
)
DYNAMIC_KEY_RE = re.compile(r"\$\{|\+|\\")  # $-интерполяция, конкатенация, \


@dataclass
class Usage:
    file: Path        # относительный путь от ROOT
    line: int
    raw_key: str
    namespace: str | None  # резолвленный итоговый namespace (или None)
    explicit_ns: str | None  # из 3-го аргумента
    class_ns: str | None     # из static i18nNamespace класса


@dataclass
class Stats:
    files_scanned: int = 0
    calls_total: int = 0
    calls_dynamic: int = 0
    calls_static: int = 0


@dataclass
class BundleIndex:
    """Индекс бандлов одной локали."""
    bundles: dict[str, dict] = field(default_factory=dict)  # ns -> json

    def lookup(self, key: str, namespace: str | None) -> bool:
        """True, если ключ резолвится в этой локали."""
        path = key.split(".")
        if not path:
            return False
        # a) прямой путь от корня бандла
        if self._walk_strict(self._root_view(), path) is not None:
            return True
        # b) через namespace
        if namespace and namespace in self.bundles:
            if self._walk_strict(self.bundles[namespace], path) is not None:
                return True
        return False

    def _root_view(self) -> dict:
        return self.bundles

    @staticmethod
    def _walk_strict(node, path: list[str]):
        """Возвращает значение, если по path добрались до строки/списка/объекта;
        None если путь обрывается. Поддерживает list-индексы (str(int))."""
        cur = node
        for seg in path:
            if isinstance(cur, dict):
                if seg not in cur:
                    return None
                cur = cur[seg]
            elif isinstance(cur, list):
                # допускаем числовой сегмент (динамические циклы)
                if not seg.isdigit():
                    return None
                idx = int(seg)
                if idx < 0 or idx >= len(cur):
                    return None
                cur = cur[idx]
            else:
                return None
        return cur

    def all_terminal_keys(self) -> set[str]:
        """Собирает все ns.path до строковых терминалов (для unused-проверки)."""
        result: set[str] = set()
        for ns, data in self.bundles.items():
            self._collect(data, [ns], result)
        return result

    @classmethod
    def _collect(cls, node, prefix: list[str], out: set[str]) -> None:
        if isinstance(node, str):
            out.add(".".join(prefix))
            return
        if isinstance(node, dict):
            for k, v in node.items():
                cls._collect(v, prefix + [k], out)
            return
        # list / число / bool / None — НЕ считаем терминалом для unused.
        # Списки переводов, как правило, перебираются циклом.


def load_bundles(locale: str) -> BundleIndex:
    bundles_dir = TRANSLATIONS / locale
    if not bundles_dir.is_dir():
        raise FileNotFoundError(f"check_i18n_keys: нет каталога {bundles_dir}")
    idx = BundleIndex()
    for path in sorted(bundles_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        ns = path.stem
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise SystemExit(f"check_i18n_keys: невалидный JSON {path}: {e}") from e
        if not isinstance(data, dict):
            raise SystemExit(f"check_i18n_keys: ожидается dict в корне {path}")
        idx.bundles[ns] = data
    return idx


def discover_service_namespaces(bundles: BundleIndex) -> set[str]:
    """Какие namespaces реально существуют в бандле — для default per-service."""
    return set(bundles.bundles.keys())


def list_js_files(only_app: str | None) -> list[Path]:
    files: list[Path] = []
    if only_app in (None, "all"):
        if APPS.is_dir():
            for app_dir in sorted(APPS.iterdir()):
                if not app_dir.is_dir():
                    continue
                ui = app_dir / "ui"
                if ui.is_dir():
                    files.extend(sorted(ui.rglob("*.js")))
        if CORE_LIB.is_dir():
            files.extend(sorted(CORE_LIB.rglob("*.js")))
    else:
        ui = APPS / only_app / "ui"
        if not ui.is_dir():
            raise SystemExit(f"check_i18n_keys: нет {ui}")
        files.extend(sorted(ui.rglob("*.js")))
    # отсекаем мок-файлы и debug-*
    return [p for p in files if p.name != "build-mock-config.js" and not p.name.startswith("debug-")]


def file_default_namespace(path: Path, available: set[str]) -> str | None:
    """Дефолт namespace по расположению файла."""
    rel = path.relative_to(ROOT)
    parts = rel.parts
    if len(parts) >= 2 and parts[0] == "apps":
        svc = parts[1]
        return svc if svc in available else None
    if len(parts) >= 2 and parts[0] == "core":
        return "platform" if "platform" in available else None
    return None


def parse_namespace_from_args(rest: str) -> str | None:
    """3-й (или 4-й) аргумент: I18nNs.X, строковый литерал или None если
    аргумент динамический (переменная). rest — то, что в скобках после ключа,
    без обрамляющих скобок, включая запятую перед vars.

    Возвращает специальный маркер "__dynamic__" если 3-й аргумент — переменная;
    вызов следует считать невозможным для статического резолва."""
    m = re.search(r"I18nNs\.([A-Z_]+)", rest)
    if m:
        const = m.group(1)
        return I18N_NS_MAP.get(const)
    m = re.search(r",\s*['\"]([a-z][a-z0-9_]*)['\"]\s*\)?\s*$", rest)
    if m:
        return m.group(1)
    m = re.search(r",\s*[^,\s][^,]*,\s*([A-Za-z_$][\w$.]*)\s*$", rest)
    if m and m.group(1) not in ("undefined", "null"):
        return "__dynamic__"
    return None


def is_dynamic_key(quote: str, body: str) -> bool:
    if quote == "`":
        return "${" in body
    return DYNAMIC_KEY_RE.search(body) is not None


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def scan_file(path: Path, available: set[str], stats: Stats) -> list[Usage]:
    text = path.read_text(encoding="utf-8")
    class_ns_match = CLASS_NS_RE.search(text)
    if class_ns_match:
        if class_ns_match.group(1):
            class_ns = I18N_NS_MAP.get(class_ns_match.group(1))
        else:
            class_ns = class_ns_match.group(2)
    else:
        class_ns = None
    default_ns = file_default_namespace(path, available)

    usages: list[Usage] = []
    for m in CALL_RE.finditer(text):
        stats.calls_total += 1
        quote = m.group(1)
        body = m.group(2)
        rest = m.group(3) or ""
        if is_dynamic_key(quote, body):
            stats.calls_dynamic += 1
            continue
        if "." not in body and not body.strip():
            continue
        explicit_ns = parse_namespace_from_args(rest)
        if explicit_ns == "__dynamic__":
            stats.calls_dynamic += 1
            continue
        stats.calls_static += 1
        ns = explicit_ns or class_ns or default_ns
        usages.append(
            Usage(
                file=path.relative_to(ROOT),
                line=line_of(text, m.start()),
                raw_key=body,
                namespace=ns,
                explicit_ns=explicit_ns,
                class_ns=class_ns,
            )
        )
    return usages


def used_terminal_keys(usages: list[Usage]) -> set[str]:
    """Нормализуем: returned `ns.path` для каждого usage.
    Если key уже начинается с известного ns — оставляем как есть.
    Если ns известен — добавляем префикс."""
    result: set[str] = set()
    for u in usages:
        result.add(u.raw_key)  # для прямого лукапа от корня
        if u.namespace:
            # префиксируем
            result.add(f"{u.namespace}.{u.raw_key}")
    return result


def find_missing(usages: list[Usage], indexes: dict[str, BundleIndex]) -> list[Usage]:
    missing: list[Usage] = []
    for u in usages:
        ok = False
        for locale in LOCALES:
            if indexes[locale].lookup(u.raw_key, u.namespace):
                ok = True
                break
        if not ok:
            missing.append(u)
    return missing


def find_unused(used: set[str], indexes: dict[str, BundleIndex]) -> dict[str, set[str]]:
    """Per-locale unused: ключи бандла, которые код не дёргает ни прямо, ни через ns."""
    result: dict[str, set[str]] = {}
    for locale in LOCALES:
        idx = indexes[locale]
        all_keys = idx.all_terminal_keys()
        unused: set[str] = set()
        for fullkey in all_keys:
            # fullkey = "ns.a.b.c"; кандидатные совпадения с used:
            #   1) сам fullkey (если код вызывал t('ns.a.b.c'))
            #   2) "a.b.c" (если код вызывал t('a.b.c') c default ns)
            ns, _, sub = fullkey.partition(".")
            candidates = {fullkey, sub}
            if any(c in used for c in candidates):
                continue
            # учитываем, что часть терминалов может быть "под динамикой":
            # если родитель fullkey содержит сегмент из DYNAMIC_LIST_HINTS,
            # вероятно достается через цикл (а DYNAMIC_KEY мы пропустили).
            segments = fullkey.split(".")
            if any(s in DYNAMIC_LIST_HINTS for s in segments):
                continue
            if _unused_scan_excluded(fullkey):
                continue
            unused.add(fullkey)
        result[locale] = unused
    return result


def collect_scan(only_app: str | None) -> tuple[dict[str, BundleIndex], list[Usage], Stats]:
    """Загрузка бандлов и скан JS для cross-check (используется clean_i18n_unused)."""
    indexes = {loc: load_bundles(loc) for loc in LOCALES}
    available_ns = set()
    for idx in indexes.values():
        available_ns |= discover_service_namespaces(idx)

    files = list_js_files(only_app)
    stats = Stats()
    all_usages: list[Usage] = []
    for f in files:
        stats.files_scanned += 1
        all_usages.extend(scan_file(f, available_ns, stats))
    return indexes, all_usages, stats


def common_unused_terminal_keys(all_usages: list[Usage], indexes: dict[str, BundleIndex]) -> set[str]:
    used = used_terminal_keys(all_usages)
    unused_per_locale = find_unused(used, indexes)
    if not LOCALES:
        return set()
    return set.intersection(*(unused_per_locale[l] for l in LOCALES))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=("missing", "unused", "all"), default="all")
    parser.add_argument("--app", default="all", help="apps/<name>/ui (или all)")
    parser.add_argument("--strict", action="store_true", help="exit 1 при наличии находок")
    parser.add_argument("--show-skipped", action="store_true", help="показать счётчик dynamic")
    args = parser.parse_args()

    only = None if args.app == "all" else args.app
    indexes, all_usages, stats = collect_scan(only)

    print(f"check_i18n_keys: файлов отсканировано {stats.files_scanned}, "
          f"вызовов t(): {stats.calls_total} (статических {stats.calls_static}, динамических {stats.calls_dynamic})")

    exit_code = 0

    if args.mode in ("missing", "all"):
        missing = find_missing(all_usages, indexes)
        print("")
        print(f"== MISSING (нет ни в ru, ни в en): {len(missing)} ==")
        # группировка по ключу
        by_key: dict[tuple[str, str | None], list[Usage]] = {}
        for u in missing:
            by_key.setdefault((u.raw_key, u.namespace), []).append(u)
        for (k, ns), uses in sorted(by_key.items(), key=lambda x: (x[0][1] or "", x[0][0])):
            ns_disp = ns or "<no-ns>"
            print(f"  [{ns_disp}] {k}")
            for u in uses[:5]:
                print(f"      {u.file}:{u.line}")
            if len(uses) > 5:
                print(f"      ... ({len(uses) - 5} more)")
        if missing:
            exit_code = 1 if args.strict else exit_code

    if args.mode in ("unused", "all"):
        used = used_terminal_keys(all_usages)
        unused_per_locale = find_unused(used, indexes)
        print("")
        common = common_unused_terminal_keys(all_usages, indexes)
        print(f"== UNUSED (есть в ru И en, но код не дёргает): {len(common)} ==")
        for k in sorted(common):
            print(f"  {k}")
        # для информации показываем разницу
        for locale in LOCALES:
            extra = unused_per_locale[locale] - common
            if extra:
                print(f"  [{locale}] доп. unused (нет в другом локали или хвост): {len(extra)}")
        if common:
            exit_code = 1 if args.strict else exit_code

    if args.show_skipped and stats.calls_dynamic:
        print("")
        print(f"== DYNAMIC (пропущено): {stats.calls_dynamic} вызовов ==")

    return exit_code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FileNotFoundError as e:
        print(f"check_i18n_keys: {e}", file=sys.stderr)
        raise SystemExit(2)
