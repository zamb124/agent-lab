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
    MAX_HEADING_LEVEL,
    WIKI_MARKS,
    WIKI_NODES,
    WikiCalloutTone,
    WikiMentionKind,
    WikiTableAlign,
    schema_as_json,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    REPO_ROOT / "core" / "frontend" / "static" / "assets" / "prosemirror" / "wiki-schema.json"
)


def test_generated_schema_file_matches_python_source():
    result = subprocess.run(
        [sys.executable, "scripts/generate/wiki_prosemirror_schema.py", "--check"],
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
    assert payload["table_aligns"] == [member.value for member in WikiTableAlign]


def test_heading_covers_every_markdown_level():
    # Меньше шести — значит терять h5 и h6 при импорте.
    assert schema_as_json()["max_heading_level"] == 6
    assert MAX_HEADING_LEVEL == 6


def test_footnote_and_math_nodes_require_their_payload():
    assert WIKI_NODES["footnote_reference"].attrs["label"].required is True
    assert WIKI_NODES["footnote_definition"].attrs["label"].required is True
    assert WIKI_NODES["math_inline"].attrs["formula"].required is True
    assert WIKI_NODES["math_block"].attrs["formula"].required is True


def test_table_cells_carry_alignment():
    for node_type in ("table_cell", "table_header"):
        assert WIKI_NODES[node_type].attrs["align"].default == ""


def test_table_cells_colwidth_is_int_list():
    # prosemirror-tables: colwidth = number[] | null, не скаляр.
    for node_type in ("table_cell", "table_header"):
        assert WIKI_NODES[node_type].attrs["colwidth"].kind.value == "int_list"
        assert WIKI_NODES[node_type].attrs["colwidth"].default is None

def test_paragraph_is_the_first_block_of_its_group():
    """ProseMirror берёт первый узел группы как заполнитель пустого контейнера.

    Если первым окажется блок с `content: block+`, автозаполнение ячейки таблицы
    уходит в бесконечную рекурсию.
    """
    block_nodes = [name for name, spec in WIKI_NODES.items() if spec.group == "block"]
    assert block_nodes[0] == "paragraph"


def test_document_root_and_text_nodes_present():
    assert WIKI_NODES["doc"].content == "block+"
    assert WIKI_NODES["text"].inline is True


def test_mention_and_file_nodes_require_target():
    assert WIKI_NODES["platform_mention"].attrs["target_id"].required is True
    assert WIKI_NODES["platform_file"].attrs["file_id"].required is True


def test_code_block_forbids_marks():
    # Разметка внутри кода превратила бы листинг в форматированный текст.
    assert WIKI_NODES["code_block"].marks == ""
