"""Резолв text presentation subtype (code / html / markdown) по имени и MIME."""

from __future__ import annotations

from pathlib import Path

from core.documents.viewer.models import TextPresentation, TextViewMode

_HTML_EXTENSIONS = frozenset({".html", ".htm"})
_MARKDOWN_EXTENSIONS = frozenset({".md", ".markdown"})
_HTML_CONTENT_TYPES = frozenset({"text/html"})
_MARKDOWN_CONTENT_TYPES = frozenset({"text/markdown", "text/x-markdown"})


def resolve_text_presentation(
    *,
    original_name: str,
    content_type: str,
) -> tuple[TextPresentation, TextViewMode]:
    """Определяет presentation и default_view_mode для text handler."""
    normalized_type = content_type.split(";", 1)[0].strip().lower()
    extension = Path(original_name).suffix.lower()
    if extension in _HTML_EXTENSIONS or normalized_type in _HTML_CONTENT_TYPES:
        return "html", "preview"
    if extension in _MARKDOWN_EXTENSIONS or normalized_type in _MARKDOWN_CONTENT_TYPES:
        return "markdown", "preview"
    return "code", "source"
