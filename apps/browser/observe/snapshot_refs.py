"""
Построение компактного accessibility snapshot с refs для детерминированных действий.

Формат вдохновлён практикой agent-browser / Playwright MCP:
- snapshot (text) минимален для LLM-контекста
- refs (json) даёт машинный маппинг ref -> (role, name, nth)

Клиент взаимодействует только через ref (`@e1`), без CSS-селекторов.
"""

from __future__ import annotations

from typing import Any, Iterable


def parse_ref(value: str) -> str:
    v = value.strip()
    if not v:
        raise ValueError("ref должен быть непустой строкой")
    if v.startswith("@"):
        v = v[1:]
    if v.startswith("ref="):
        v = v[len("ref=") :]
    if not (v.startswith("e") and v[1:].isdigit()):
        raise ValueError(f"Неверный ref: {value!r} (ожидался @eN)")
    return v


_INTERACTIVE_ROLES: set[str] = {
    "button",
    "link",
    "textbox",
    "searchbox",
    "checkbox",
    "radio",
    "combobox",
    "listbox",
    "menuitem",
    "option",
    "switch",
    "tab",
    "slider",
    "spinbutton",
}


def _str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    return str(v)


def _iter_children(node: dict[str, Any]) -> Iterable[dict[str, Any]]:
    ch = node.get("children")
    if not isinstance(ch, list):
        return []
    out: list[dict[str, Any]] = []
    for c in ch:
        if isinstance(c, dict):
            out.append(c)
    return out


def build_interactive_snapshot_with_refs(ax_tree: dict[str, Any]) -> tuple[str, dict[str, dict[str, Any]]]:
    """
    Построить компактный snapshot из accessibility tree.

    Выход:
    - snapshot: текст, одна строка на элемент
    - refs: json map вида {"e1": {"role": "...", "name": "...", "nth": 0}, ...}

    nth — индекс среди элементов с тем же (role, name) в рамках текущего snapshot.
    """
    if not isinstance(ax_tree, dict):
        raise ValueError("ax_tree должен быть dict")

    ref_counter = 0
    seen_counts: dict[tuple[str, str], int] = {}
    lines: list[str] = []
    refs: dict[str, dict[str, Any]] = {}

    def next_ref() -> str:
        nonlocal ref_counter
        ref_counter += 1
        return f"e{ref_counter}"

    def walk(n: dict[str, Any]) -> None:
        role = _str(n.get("role")).lower()
        name = _str(n.get("name")).strip()
        value = _str(n.get("value")).strip()
        if role in _INTERACTIVE_ROLES:
            key = (role, name)
            nth = seen_counts.get(key, 0)
            seen_counts[key] = nth + 1
            ref = next_ref()
            refs[ref] = {"role": role, "name": name, "nth": nth}
            if value:
                refs[ref]["value"] = value
            # agent-browser style: "- role "Name" [ref=eN]"
            if name:
                if value:
                    lines.append(f'- {role} "{name}" [ref={ref}] ({value})')
                else:
                    lines.append(f'- {role} "{name}" [ref={ref}]')
            else:
                lines.append(f"- {role} [ref={ref}]")
        for c in _iter_children(n):
            walk(c)

    walk(ax_tree)
    if not lines:
        return "(no interactive elements)", {}
    return "\n".join(lines), refs

