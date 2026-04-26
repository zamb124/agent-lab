"""
Visibility tree из AX snapshot: приоритет интерактивных ролей и лимит budget.

Чистые функции для unit-тестов без Playwright.
"""

from __future__ import annotations

from typing import Any

from apps.browser.control.types import VISIBILITY_TREE_SCHEMA_VERSION

# Роли с приоритетом для интерактивных действий (baseline).
_INTERACTIVE_ROLE_PRIORITY: dict[str, int] = {
    "textbox": 0,
    "searchbox": 0,
    "combobox": 1,
    "listbox": 2,
    "button": 3,
    "menuitem": 4,
    "link": 5,
    "checkbox": 6,
    "radio": 7,
    "tab": 8,
    "switch": 9,
    "slider": 10,
    "spinbutton": 11,
}


def _role_priority(role: str | None) -> int:
    if not role:
        return 100
    r = role.lower()
    if r in _INTERACTIVE_ROLE_PRIORITY:
        return _INTERACTIVE_ROLE_PRIORITY[r]
    if r in ("heading", "main", "navigation", "form", "article"):
        return 50
    if r == "statictext" or r == "text":
        return 80
    return 90


def _node_name(node: dict[str, Any]) -> str:
    name = node.get("name")
    if isinstance(name, str):
        return name
    return ""


def flatten_ax_nodes(
    root: dict[str, Any] | None,
    *,
    path_prefix: str = "",
) -> list[dict[str, Any]]:
    """
    Плоский список узлов с полями role, name, value, ref (путь), children отброшены.
    """
    if root is None:
        return []
    out: list[dict[str, Any]] = []

    def walk(n: dict[str, Any], path: str) -> None:
        role = n.get("role")
        role_s = role if isinstance(role, str) else ""
        name = _node_name(n)
        value = n.get("value")
        value_out: str | None
        if value is None:
            value_out = None
        elif isinstance(value, str):
            value_out = value
        else:
            value_out = str(value)
        entry: dict[str, Any] = {
            "ref": path,
            "role": role_s,
            "name": name,
        }
        if value_out is not None:
            entry["value"] = value_out
        out.append(entry)
        children = n.get("children")
        if not isinstance(children, list):
            return
        for i, ch in enumerate(children):
            if isinstance(ch, dict):
                walk(ch, f"{path}.{i}" if path else str(i))

    walk(root, path_prefix)
    return out


def prune_visibility_nodes(
    flat: list[dict[str, Any]],
    *,
    budget: int,
    url: str,
) -> dict[str, Any]:
    """
    Упорядочить по приоритету интерактивности и обрезать до budget узлов.
    """
    if budget <= 0:
        raise ValueError("budget должен быть положительным")
    scored: list[tuple[int, int, dict[str, Any]]] = []
    for idx, node in enumerate(flat):
        role = node.get("role", "")
        role_s = role if isinstance(role, str) else ""
        pr = _role_priority(role_s)
        scored.append((pr, idx, node))
    scored.sort(key=lambda t: (t[0], t[1]))
    picked = [t[2] for t in scored[:budget]]
    nodes: list[dict[str, Any]] = []
    for i, n in enumerate(picked):
        item = {
            "ref": n["ref"],
            "role": n["role"],
            "name": n["name"],
        }
        if "value" in n:
            item["value"] = n["value"]
        item["llm_index"] = i
        nodes.append(item)
    return {
        "schema": VISIBILITY_TREE_SCHEMA_VERSION,
        "url": url,
        "budget": budget,
        "node_count": len(nodes),
        "nodes": nodes,
    }
