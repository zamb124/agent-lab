"""strip_outer_markdown_code_fence."""

from __future__ import annotations

from core.text_transforms.strip_outer_markdown_fence import strip_outer_markdown_code_fence


def test_strip_outer_fence_markdown_lang() -> None:
    raw = "```markdown\n### Hi\n\n**x**\n```"
    assert strip_outer_markdown_code_fence(raw) == "### Hi\n\n**x**"


def test_strip_outer_fence_no_lang() -> None:
    raw = "```\nline\n```"
    assert strip_outer_markdown_code_fence(raw) == "line"


def test_no_fence_trim_only() -> None:
    raw = "  plain  "
    assert strip_outer_markdown_code_fence(raw) == "plain"


def test_inner_nested_fence_preserved() -> None:
    raw = "```markdown\nbefore\n```py\nx\n```\nafter\n```"
    assert "```py" in strip_outer_markdown_code_fence(raw)
