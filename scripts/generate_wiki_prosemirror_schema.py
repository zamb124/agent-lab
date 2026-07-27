#!/usr/bin/env python3
"""Сгенерировать схему документа wiki для браузерного редактора.

Схема описана один раз в `apps/wiki/content/schema.py`; браузер собирает свой
`Schema` из этого JSON. Гейт `--check` не даёт коду и редактору разойтись:
разошедшиеся схемы означают документы, которые сервер считает валидными, а
редактор не открывает.

Usage:
    uv run python scripts/generate_wiki_prosemirror_schema.py
    uv run python scripts/generate_wiki_prosemirror_schema.py --check
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    REPO_ROOT / "core" / "frontend" / "static" / "assets" / "prosemirror" / "wiki-schema.json"
)

sys.path.insert(0, str(REPO_ROOT))

from apps.wiki.content.schema import schema_as_json  # noqa: E402

HEADER_NOTE = (
    "Сгенерировано scripts/generate_wiki_prosemirror_schema.py из "
    "apps/wiki/content/schema.py. Не редактировать вручную."
)


def render() -> str:
    payload = schema_as_json()
    payload["_note"] = HEADER_NOTE
    # Ключи не сортируются: ProseMirror берёт первый узел группы как заполнитель
    # пустого контейнера, поэтому порядок узлов из WIKI_NODES значим. При
    # сортировке первым блоком становится blockquote, и авто-заполнение ячейки
    # таблицы уходит в бесконечную рекурсию.
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument(
        "--check",
        action="store_true",
        help="Проверить актуальность файла без записи (для CI).",
    )
    args = parser.parse_args()
    rendered = render()

    if args.check:
        if not SCHEMA_PATH.exists():
            print(f"FAIL: {SCHEMA_PATH.relative_to(REPO_ROOT)} отсутствует", file=sys.stderr)
            return 1
        current = SCHEMA_PATH.read_text(encoding="utf-8")
        if current != rendered:
            print(
                f"FAIL: {SCHEMA_PATH.relative_to(REPO_ROOT)} устарел; "
                "запустите scripts/generate_wiki_prosemirror_schema.py",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {SCHEMA_PATH.relative_to(REPO_ROOT)} актуален")
        return 0

    SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
    _ = SCHEMA_PATH.write_text(rendered, encoding="utf-8")
    print(f"WROTE: {SCHEMA_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
