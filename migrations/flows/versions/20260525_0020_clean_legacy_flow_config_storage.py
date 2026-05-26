"""clean legacy FlowConfig storage payloads

Revision ID: 20260525_0020
Revises: 20260525_0019
Create Date: 2026-05-25
"""

from __future__ import annotations

import ast
import copy
import json
import re
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "20260525_0020"
down_revision = "20260525_0019"
branch_labels = None
depends_on = None

_LEGACY_TOP_LEVEL_KEYS = ("mock", "evaluation", "auth_headers")
_LEGACY_BRANCH_KEYS = ("mock",)
_CONDITION_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_.]*)\s*(==|!=|>=|<=|>|<|in)\s*(.+?)\s*$")


def _parse_legacy_condition_value(raw_value: str) -> Any:
    raw = raw_value.strip()
    if raw == "true":
        return True
    if raw == "false":
        return False
    if raw == "null":
        return None
    try:
        return ast.literal_eval(raw)
    except (SyntaxError, ValueError) as exc:
        raise ValueError(f"unsupported legacy edge condition value: {raw_value!r}") from exc


def _parse_legacy_simple_condition(condition: str) -> dict[str, Any]:
    match = _CONDITION_RE.match(condition)
    if match is None:
        raise ValueError(f"unsupported legacy edge condition: {condition!r}")
    variable = match.group(1)
    operator = match.group(2)
    raw_value = match.group(3)
    return {
        "type": "simple",
        "variable": variable,
        "operator": operator,
        "value": _parse_legacy_condition_value(raw_value),
    }


def _normalize_edges(raw_edges: Any) -> tuple[Any, bool]:
    if not isinstance(raw_edges, list):
        return raw_edges, False

    changed = False
    edges: list[Any] = []
    for raw_edge in raw_edges:
        if not isinstance(raw_edge, dict):
            edges.append(raw_edge)
            continue
        edge = copy.deepcopy(raw_edge)
        condition = edge.get("condition")
        if isinstance(condition, str):
            edge["condition"] = _parse_legacy_simple_condition(condition)
            changed = True
        edges.append(edge)
    return edges, changed


def _migrate_branch_payload(raw_branch: Any) -> tuple[Any, bool]:
    if not isinstance(raw_branch, dict):
        return raw_branch, False

    branch = copy.deepcopy(raw_branch)
    changed = False
    for legacy_key in _LEGACY_BRANCH_KEYS:
        if legacy_key in branch:
            del branch[legacy_key]
            changed = True

    normalized_edges, edges_changed = _normalize_edges(branch.get("edges"))
    if edges_changed:
        branch["edges"] = normalized_edges
        changed = True

    return branch, changed


def _migrate_flow_payload(value: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    out = copy.deepcopy(value)
    changed = False

    for legacy_key in _LEGACY_TOP_LEVEL_KEYS:
        if legacy_key in out:
            del out[legacy_key]
            changed = True

    normalized_edges, edges_changed = _normalize_edges(out.get("edges"))
    if edges_changed:
        out["edges"] = normalized_edges
        changed = True

    raw_branches = out.get("branches")
    if isinstance(raw_branches, dict):
        branches: dict[str, Any] = {}
        branches_changed = False
        for branch_id, raw_branch in raw_branches.items():
            branch, branch_changed = _migrate_branch_payload(raw_branch)
            branches[branch_id] = branch
            branches_changed = branches_changed or branch_changed
        if branches_changed:
            out["branches"] = branches
            changed = True

    return out, changed


def _migrate_table(table: str) -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text(f"SELECT key, value FROM {table} WHERE key LIKE :prefix"), {"prefix": "company:%:flow:%"}).fetchall()
    for row in rows:
        key = row[0]
        value = row[1]
        if not isinstance(value, dict):
            continue
        new_value, changed = _migrate_flow_payload(value)
        if not changed:
            continue
        conn.execute(
            sa.text(f"UPDATE {table} SET value = CAST(:payload AS jsonb) WHERE key = :key"),
            {"payload": json.dumps(new_value, ensure_ascii=False), "key": key},
        )


def upgrade() -> None:
    _migrate_table("flows")
    _migrate_table("flows_versions")


def downgrade() -> None:
    pass
