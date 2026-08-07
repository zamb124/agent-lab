"""Stage G acceptance matrix scaffolds (plan §25.8 / §22).

Executable checks that can run without browser for publish/continuity contracts.
Zero-pixel / a11y / perf budgets live in marked e2e modules and expand from here.
"""

from __future__ import annotations

from core.models.flow_interface import build_default_chat_document
from core.state.flow_ui_publish import validate_flow_ui_publish

ACCEPTANCE_VIEWPORTS = (
    "mobile-compact",
    "tablet-medium",
    "desktop-wide",
    "embed-inline",
)

ACCEPTANCE_SURFACES = ("page", "panel", "drawer", "inline")

ACCEPTANCE_THEMES = ("light", "dark")

ACCEPTANCE_LOCALES = ("ru", "en")


def test_default_template_publish_matrix_gate() -> None:
    """Publish gate must pass for the default chat template across acceptance axes.

    Viewport/surface/theme/locale are render-context axes; the document itself
    must remain publishable independently of those axes.
    """
    document = build_default_chat_document()
    problems = validate_flow_ui_publish(document)
    assert problems == []
    assert ACCEPTANCE_VIEWPORTS
    assert ACCEPTANCE_SURFACES
    assert ACCEPTANCE_THEMES
    assert ACCEPTANCE_LOCALES


def test_acceptance_matrix_cardinality() -> None:
    combinations = (
        len(ACCEPTANCE_VIEWPORTS)
        * len(ACCEPTANCE_SURFACES)
        * len(ACCEPTANCE_THEMES)
        * len(ACCEPTANCE_LOCALES)
    )
    # 4 * 4 * 2 * 2 = 64 mandatory scenarios for zero-pixel suite expansion
    assert combinations == 64
