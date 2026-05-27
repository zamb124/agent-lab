from __future__ import annotations

from apps.flows.tools.web_browser import bound_browser_markdown


def test_bounded_markdown_keeps_short_text_unchanged() -> None:
    markdown = "# Title\n\nShort page."

    bounded, truncated = bound_browser_markdown(markdown, 100)

    assert bounded == markdown
    assert truncated is False


def test_bounded_markdown_truncates_with_metadata() -> None:
    markdown = "x" * 240

    bounded, truncated = bound_browser_markdown(markdown, 120)

    assert truncated is True
    assert len(bounded) <= 120
    assert "markdown truncated" in bounded
    assert "original_chars=240" in bounded
    assert "max_markdown_chars=120" in bounded
