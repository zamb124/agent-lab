"""Разбор ``source`` блока ``html``: декларативные привязки ``data-bind`` / ``data-show``.

Пути этих атрибутов входят в проекцию state блока наравне с ``fields``; их же
использует publish gate, чтобы отклонить привязку к frozen/системному полю.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import override

from core.flow_ui.document import STATE_PATH_PATTERN

HTML_BIND_ATTRIBUTE = "data-bind"
HTML_SHOW_ATTRIBUTE = "data-show"

_STATE_PATH_RE = re.compile(STATE_PATH_PATTERN)


class _BindingCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.paths: list[str] = []
        self.invalid: list[str] = []

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name not in (HTML_BIND_ATTRIBUTE, HTML_SHOW_ATTRIBUTE):
                continue
            path = (value or "").strip()
            if not _STATE_PATH_RE.match(path):
                self.invalid.append(f"{name}={value!r}")
                continue
            if path not in self.paths:
                self.paths.append(path)


def html_bound_paths(source: str) -> list[str]:
    """Пути state из ``data-bind``/``data-show`` в порядке появления.

    Невалидный путь — ошибка автора блока, а не данных, поэтому здесь ``raise``.
    """

    collector = _BindingCollector()
    collector.feed(source)
    collector.close()
    if collector.invalid:
        raise ValueError("html block: invalid state path in " + ", ".join(collector.invalid))
    return collector.paths


__all__ = ["HTML_BIND_ATTRIBUTE", "HTML_SHOW_ATTRIBUTE", "html_bound_paths"]
