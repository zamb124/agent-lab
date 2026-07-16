"""Tests for MarkdownHeadingParser (§4.1.1)."""

from __future__ import annotations

from core.search.markdown_headings import ParsedSection, parse_sections


def test_parse_two_h2_sections() -> None:
    md = "# Article\n\nIntro text.\n\n## Section A\n\nA body text.\n\n## Section B\n\nB body text.\n"
    sections = parse_sections(md, max_section_tokens=200)
    titles = [s.section_title for s in sections]
    assert "Article" in titles
    assert "Section A" in titles
    assert "Section B" in titles


def test_heading_trail_nested() -> None:
    md = "## Parent\n\nParent text.\n\n### Child\n\nChild text.\n"
    sections = parse_sections(md, max_section_tokens=200)
    child_section = next((s for s in sections if s.section_title == "Child"), None)
    assert child_section is not None
    assert "Parent" in child_section.heading_trail


def test_h4_absorbed_as_body() -> None:
    md = "## Section\n\n#### DeepHeading\n\nDeep content here.\n"
    sections = parse_sections(md, max_section_tokens=200)
    # H4 should be treated as body text, not a separate section
    assert not any(s.section_title == "DeepHeading" for s in sections)
    section = next(s for s in sections if s.section_title == "Section")
    assert "DeepHeading" in section.text or "Deep" in section.text


def test_no_headings_returns_single_section() -> None:
    md = "Just plain text without any headings here.\n"
    sections = parse_sections(md, max_section_tokens=200)
    assert len(sections) == 1
    assert sections[0].section_title == ""
    assert "plain text" in sections[0].text


def test_max_section_tokens_caps_text() -> None:
    md = "## Section\n\n" + " ".join(f"word{i}" for i in range(500)) + "\n"
    sections = parse_sections(md, max_section_tokens=50)
    body_section = next((s for s in sections if s.section_title == "Section"), None)
    assert body_section is not None
    word_count = len(body_section.text.split())
    assert word_count <= 50


def test_level_tracked_correctly() -> None:
    md = "# H1\n\nText.\n\n## H2\n\nText.\n"
    sections = parse_sections(md)
    h1 = next(s for s in sections if s.section_title == "H1")
    h2 = next(s for s in sections if s.section_title == "H2")
    assert h1.level == 1
    assert h2.level == 2


def test_empty_markdown_returns_single_empty_section() -> None:
    sections = parse_sections("")
    assert len(sections) == 1
    assert isinstance(sections[0], ParsedSection)
