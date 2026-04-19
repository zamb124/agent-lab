"""One-shot cleanup of `core/i18n/translations/{ru,en}/flows.json`.

Удаляет:
  1. Все unused-ключи (которые код больше не дёргает) — вычисляются
     scripts/check_i18n_keys.py.
  2. Все секции с суффиксом `_legacy` (явный мусор от рефакторинга).

Также схлопывает дубликаты top-level ключей (json.load+object_pairs_hook
ловит, обычный json.load молча перезаписывает) — оставляем merged.

Запуск: `uv run python scripts/_clean_flows_i18n.py`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RU = ROOT / "core/i18n/translations/ru/flows.json"
EN = ROOT / "core/i18n/translations/en/flows.json"


def merge_duplicates(pairs):
    """object_pairs_hook: объединяет повторяющиеся top-level ключи в один merge dict."""
    merged: OrderedDict = OrderedDict()
    for k, v in pairs:
        if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
            merged[k] = {**merged[k], **v}
        else:
            merged[k] = v
    return merged


def collect_used_keys() -> set[str]:
    """Берём список UNUSED для flows и исключаем из бандла."""
    out = subprocess.check_output(
        [
            "uv", "run", "python", "scripts/check_i18n_keys.py",
            "--mode", "unused", "--app", "flows",
        ],
        cwd=ROOT,
    ).decode("utf-8", errors="replace")
    unused = set()
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("flows.") and "  " not in line:
            unused.add(line[len("flows."):])
    return unused


def prune(node, prefix: list[str], unused: set[str]):
    """Удаляет ключи, чьи полные пути входят в `unused`. Возвращает очищенный dict."""
    if not isinstance(node, dict):
        return node
    cleaned: OrderedDict = OrderedDict()
    for k, v in node.items():
        full = ".".join(prefix + [k])
        if isinstance(v, dict):
            sub = prune(v, prefix + [k], unused)
            if sub:
                cleaned[k] = sub
        elif full in unused:
            continue
        else:
            cleaned[k] = v
    return cleaned


def drop_legacy(node):
    if not isinstance(node, dict):
        return node
    return OrderedDict(
        (k, drop_legacy(v))
        for k, v in node.items()
        if not (isinstance(k, str) and k.endswith("_legacy"))
    )


def process(path: Path, unused: set[str]) -> int:
    raw = path.read_text()
    data = json.loads(raw, object_pairs_hook=merge_duplicates)
    data = drop_legacy(data)
    cleaned = prune(data, [], unused)
    out = json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n"
    path.write_text(out)
    return len(out.splitlines())


def main() -> int:
    unused = collect_used_keys()
    print(f"unused keys to drop: {len(unused)}")
    ru_lines = process(RU, unused)
    en_lines = process(EN, unused)
    print(f"ru lines: {ru_lines}, en lines: {en_lines}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
