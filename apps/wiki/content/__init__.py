"""
Контент страницы: схема документа и конвертеры.

`ProseMirrorNode` — источник правды содержимого. Markdown выводится из него
сериализатором и разбирается обратно парсером; писать markdown в обход этих
двух модулей нельзя, иначе представления разойдутся.
"""

from apps.wiki.content.markdown_parser import WikiMarkdownError, markdown_to_document
from apps.wiki.content.markdown_serializer import (
    document_to_markdown,
    document_to_plain_text,
)
from apps.wiki.content.prosemirror import (
    ProseMirrorMark,
    ProseMirrorNode,
    empty_document,
    text_node,
)
from apps.wiki.content.schema import (
    WikiCalloutTone,
    WikiMentionKind,
    WikiSchemaError,
    normalize_document,
    schema_as_json,
)

__all__ = [
    "ProseMirrorMark",
    "ProseMirrorNode",
    "WikiCalloutTone",
    "WikiMarkdownError",
    "WikiMentionKind",
    "WikiSchemaError",
    "document_to_markdown",
    "document_to_plain_text",
    "empty_document",
    "markdown_to_document",
    "normalize_document",
    "schema_as_json",
    "text_node",
]
