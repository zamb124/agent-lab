"""Unit: baseline visibility из AX-подобного дерева (без Playwright)."""

from __future__ import annotations

from apps.browser.control.ax_visibility import flatten_ax_nodes, prune_visibility_nodes


def test_prune_visibility_respects_budget_and_prioritizes_button() -> None:
    tree = {
        "role": "WebArea",
        "name": "x",
        "children": [
            {"role": "StaticText", "name": "filler"},
            {"role": "button", "name": "Go"},
            {"role": "link", "name": "About"},
        ],
    }
    flat = flatten_ax_nodes(tree)
    out = prune_visibility_nodes(flat, budget=2, url="https://example.com/")
    roles = [n["role"] for n in out["nodes"]]
    assert len(roles) == 2
    assert "button" in roles
    assert out["schema"].startswith("browser.control.visibility")
