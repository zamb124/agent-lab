#!/usr/bin/env python3
"""
Удаляет из core/i18n/translations/{ru,en}/*.json терминальные строковые ключи,
которые check_i18n_keys считает common-unused (есть в ru и en, нет статического t()).

Динамические деревья и toast-ключи не трогаются (регексы ниже). Файлы с именем,
начинающимся на «_», не обрабатываются (как в check_i18n_keys).

Запуск:
  uv run python scripts/clean_i18n_unused.py
  uv run python scripts/clean_i18n_unused.py --apply

По умолчанию только отчёт. После --apply: make check-i18n и check_i18n_keys.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRANSLATIONS = ROOT / "core" / "i18n" / "translations"
LOCALES = ("ru", "en")


def _load_i18n_unused_scan_exclusions():
    name = "_i18n_unused_scan_exclusions"
    mod = sys.modules.get(name)
    if mod is not None:
        return mod
    path = ROOT / "scripts" / "i18n_unused_scan_exclusions.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("clean_i18n_unused: cannot load i18n_unused_scan_exclusions.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_check_i18n_keys():
    path = ROOT / "scripts" / "check_i18n_keys.py"
    name = "_agent_lab_check_i18n_keys"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("clean_i18n_unused: cannot load check_i18n_keys")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _protected(fullkey: str) -> bool:
    return _load_i18n_unused_scan_exclusions().terminal_key_protected_from_prune(fullkey)


def _delete_terminal(bundle: dict, parts: list[str]) -> None:
    if len(parts) < 1:
        return
    if len(parts) == 1:
        bundle.pop(parts[0], None)
        return
    head = parts[0]
    if head not in bundle or not isinstance(bundle[head], dict):
        return
    _delete_terminal(bundle[head], parts[1:])
    if isinstance(bundle[head], dict) and len(bundle[head]) == 0:
        del bundle[head]


def _split_fullkey(fullkey: str) -> tuple[str, list[str]]:
    segs = fullkey.split(".")
    if len(segs) < 2:
        raise ValueError(f"clean_i18n_unused: invalid fullkey {fullkey!r}")
    return segs[0], segs[1:]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="записать изменения в JSON")
    args = parser.parse_args()
    dry_run = not args.apply

    cik = _load_check_i18n_keys()
    indexes, all_usages, stats = cik.collect_scan(None)
    common = cik.common_unused_terminal_keys(all_usages, indexes)
    removable = sorted(k for k in common if not _protected(k))

    print(f"clean_i18n_unused: скан как check_i18n_keys, common_unused={len(common)}, к удалению={len(removable)}")
    by_file: dict[str, list[str]] = {}
    for k in removable:
        ns, _rest = _split_fullkey(k)
        by_file.setdefault(f"{ns}.json", []).append(k)

    for fname, keys in sorted(by_file.items(), key=lambda x: x[0]):
        print(f"  {fname}: {len(keys)} ключей")

    if dry_run:
        print("clean_i18n_unused: без --apply файлы не менялись")
        return 0

    changed_files: set[Path] = set()
    for loc in LOCALES:
        lang_dir = TRANSLATIONS / loc
        for fname, keys in by_file.items():
            path = lang_dir / fname
            if not path.is_file():
                print(f"clean_i18n_unused: пропуск нет файла {path}", file=sys.stderr)
                continue
            if fname.startswith("_"):
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise SystemExit(f"clean_i18n_unused: ожидался dict в корне {path}")
            before = json.dumps(data, sort_keys=True)
            for fullkey in keys:
                ns, parts = _split_fullkey(fullkey)
                if ns != path.stem:
                    raise SystemExit(f"clean_i18n_unused: namespace mismatch {fullkey!r} vs {path}")
                _delete_terminal(data, parts)
            after = json.dumps(data, sort_keys=True)
            if before != after:
                path.write_text(json.dumps(data, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
                changed_files.add(path)

    print(f"clean_i18n_unused: записано файлов: {len(changed_files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
