"""Снятие AX: CDP nodes -> дерево для flatten_ax_nodes (без Playwright)."""

from __future__ import annotations

from apps.browser.control.ax_snapshot import cdp_ax_nodes_to_tree_dict
from apps.browser.control.ax_visibility import flatten_ax_nodes


def test_cdp_ax_nodes_to_tree_dict_single_root() -> None:
    nodes = [
        {
            "nodeId": "1",
            "role": {"value": "WebArea"},
            "name": {"value": "x"},
            "childIds": ["2"],
        },
        {
            "nodeId": "2",
            "role": {"value": "button"},
            "name": {"value": "Go"},
            "backendDOMNodeId": 42,
        },
    ]
    tree = cdp_ax_nodes_to_tree_dict(nodes)
    assert tree["role"] in ("WebArea", "webarea", "generic", "")
    flat = flatten_ax_nodes(tree)
    roles = [x["role"] for x in flat]
    assert "button" in roles
    assert "Go" in [x.get("name") for x in flat]
