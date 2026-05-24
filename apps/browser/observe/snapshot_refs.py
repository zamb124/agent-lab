"""
Построение компактного accessibility snapshot с refs для детерминированных действий.

Формат вдохновлён практикой agent-browser / Playwright MCP:
- snapshot (text) минимален для LLM-контекста
- refs (json) даёт машинный маппинг ref -> (role, name, nth)

Клиент взаимодействует только через ref (`@e1`), без CSS-селекторов.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal, NotRequired, TypedDict, TypeGuard

from core.types import JsonObject

InteractiveRole = Literal[
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
]


class InteractiveSnapshotRef(TypedDict):
    role: InteractiveRole
    name: str
    nth: int
    value: NotRequired[str]


RefMap = dict[str, InteractiveSnapshotRef]


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


_INTERACTIVE_ROLES: frozenset[InteractiveRole] = frozenset({
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
})


def is_interactive_role(value: str) -> TypeGuard[InteractiveRole]:
    return value in _INTERACTIVE_ROLES


def _str(v: object) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    return str(v)


def _iter_children(node: JsonObject) -> Iterable[JsonObject]:
    ch = node.get("children")
    if not isinstance(ch, list):
        return []
    out: list[JsonObject] = []
    for c in ch:
        if isinstance(c, dict):
            out.append(c)
    return out


def build_interactive_snapshot_with_refs(ax_tree: JsonObject) -> tuple[str, RefMap]:
    """
    Построить компактный snapshot из accessibility tree.

    Выход:
    - snapshot: текст, одна строка на элемент
    - refs: json map вида {"e1": {"role": "...", "name": "...", "nth": 0}, ...}

    nth — индекс среди элементов с тем же (role, name) в рамках текущего snapshot.
    """
    ref_counter = 0
    seen_counts: dict[tuple[str, str], int] = {}
    lines: list[str] = []
    refs: RefMap = {}

    def next_ref() -> str:
        nonlocal ref_counter
        ref_counter += 1
        return f"e{ref_counter}"

    def walk(n: JsonObject) -> None:
        role = _str(n.get("role")).lower()
        name = _str(n.get("name")).strip()
        value = _str(n.get("value")).strip()
        if is_interactive_role(role):
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
