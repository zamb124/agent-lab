"""MarkdownHeadingParser: split markdown into sections by heading hierarchy (§4.1.1).

Sections are bounded by H1–H3 headings; deeper levels (H4+) are treated as body
text within the current section.  Section text is word-capped to keep embed inputs
compact.  Used by index_study strategies to build per-section vectors without
persisting prose.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_RE_HEADING_LINE = re.compile(r"^(#{1,6})\s+(.+)$")
_RE_WORDS = re.compile(r"\S+")

_MAX_PARSE_DEPTH = 3


@dataclass
class ParsedSection:
    """One heading-bounded section of a markdown document."""

    heading_trail: list[str] = field(default_factory=list)
    section_title: str = ""
    text: str = ""
    level: int = 0


def parse_sections(
    markdown: str,
    *,
    max_section_tokens: int = 200,
) -> list[ParsedSection]:
    """Parse markdown into sections delimited by H1–H3 headings.

    H4+ headings are absorbed as body text in the current section.
    Each section body is word-capped at max_section_tokens.
    If the document has no headings, returns one section with the full body.
    """
    lines = markdown.splitlines()

    # trail stack: list of (level, title) for ancestors of current section
    current_trail_stack: list[tuple[int, str]] = []
    current_title: str = ""
    current_level: int = 0
    current_body: list[str] = []
    sections: list[ParsedSection] = []

    def _flush() -> None:
        body = "\n".join(current_body).strip()
        if not current_title and not body:
            return
        words = _RE_WORDS.findall(body)
        capped = " ".join(words[:max_section_tokens]) if max_section_tokens > 0 else ""
        trail = [t for _, t in current_trail_stack]
        sections.append(
            ParsedSection(
                heading_trail=trail,
                section_title=current_title,
                text=capped,
                level=current_level,
            )
        )

    for line in lines:
        m = _RE_HEADING_LINE.match(line.strip())
        if m is None:
            current_body.append(line)
            continue

        level = len(m.group(1))
        title = m.group(2).strip()

        if level > _MAX_PARSE_DEPTH:
            # Treat as body text within current section
            current_body.append(line)
            continue

        # Flush the section that was being accumulated
        _flush()

        # Rebuild ancestor trail: drop levels >= current
        current_trail_stack = [(lvl, t) for lvl, t in current_trail_stack if lvl < level]
        current_trail_stack.append((level, title))
        current_title = title
        current_level = level
        current_body = []

    _flush()

    if not sections:
        words = _RE_WORDS.findall(markdown.strip())
        capped = " ".join(words[:max_section_tokens]) if max_section_tokens > 0 else ""
        sections.append(
            ParsedSection(
                heading_trail=[],
                section_title="",
                text=capped,
                level=0,
            )
        )

    return sections
