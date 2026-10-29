"""
Контент страницы: схема документа и конвертеры.

`ProseMirrorNode` — источник правды содержимого. Markdown выводится из него
сериализатором и разбирается обратно парсером; писать markdown в обход этих
двух модулей нельзя, иначе представления разойдутся.
"""

from apps.wiki.content.markdown_file import (
    WikiMarkdownFileParts,
    WikiMarkdownFrontMatter,
    compose_markdown_file,
    markdown_file_name,
    split_markdown_file,
)
from apps.wiki.content.markdown_notices import (
    WikiMarkdownNotice,
    WikiMarkdownNoticeKind,
)
from apps.wiki.content.markdown_parser import (
    WikiMarkdownError,
    WikiMarkdownParseResult,
    markdown_to_document,
    parse_markdown,
)
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
    WikiTableAlign,
    normalize_document_in_serialization_order,
    schema_as_json,
)

__all__ = [
    "ProseMirrorMark",
    "ProseMirrorNode",
    "WikiCalloutTone",
    "WikiMarkdownError",
    "WikiMarkdownFileParts",
    "WikiMarkdownFrontMatter",
    "WikiMarkdownNotice",
    "WikiMarkdownNoticeKind",
    "WikiMarkdownParseResult",
    "WikiMentionKind",
    "WikiSchemaError",
    "WikiTableAlign",
    "compose_markdown_file",
    "document_to_markdown",
    "document_to_plain_text",
    "empty_document",
    "markdown_file_name",
    "markdown_to_document",
    "normalize_document_in_serialization_order",
    "parse_markdown",
    "schema_as_json",
    "split_markdown_file",
    "text_node",
]
