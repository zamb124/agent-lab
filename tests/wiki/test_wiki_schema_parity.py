"""
Схема документа wiki: единственный источник и его отражение для браузера.

Схема описана в Python, а редактор собирает свой `Schema` из сгенерированного
JSON. Если файл устарел, сервер принимает документы, которые редактор открыть
не сможет, поэтому расхождение — ошибка сборки, а не мелочь.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from apps.wiki.content.schema import (
    MARK_SERIALIZATION_ORDER,
    WIKI_MARKS,
    WIKI_NODES,
    WikiCalloutTone,
    WikiMentionKind,
    schema_as_json,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    REPO_ROOT / "core" / "frontend" / "static" / "assets" / "prosemirror" / "wiki-schema.json"
)


def test_generated_schema_file_matches_python_source():
    result = subprocess.run(
        [sys.executable, "scripts/generate_wiki_prosemirror_schema.py", "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_generated_schema_lists_same_nodes_and_marks():
    payload = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert set(payload["nodes"]) == set(WIKI_NODES)
    assert set(payload["marks"]) == set(WIKI_MARKS)


def test_every_mark_has_serialization_position():
    # Без фиксированного места в порядке марка сериализовалась бы недетерминированно.
    assert set(MARK_SERIALIZATION_ORDER) == set(WIKI_MARKS)


def test_enums_are_exported_for_editor():
    payload = schema_as_json()
    assert payload["mention_kinds"] == [member.value for member in WikiMentionKind]
    assert payload["callout_tones"] == [member.value for member in WikiCalloutTone]


def test_document_root_and_text_nodes_present():
    assert WIKI_NODES["doc"].content == "block+"
    assert WIKI_NODES["text"].inline is True


def test_mention_and_file_nodes_require_target():
    assert WIKI_NODES["platform_mention"].attrs["target_id"].required is True
    assert WIKI_NODES["platform_file"].attrs["file_id"].required is True


def test_code_block_forbids_marks():
    # Разметка внутри кода превратила бы листинг в форматированный текст.
    assert WIKI_NODES["code_block"].marks == ""
