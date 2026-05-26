"""Данные flows: legacy-ключ skills -> branches

Revision ID: agents_0005
Revises: agents_0004
Create Date: 2026-05-01
"""

from __future__ import annotations

import copy
import json
from typing import Any, Dict, Sequence, Tuple, Union

import sqlalchemy as sa
from alembic import op

revision: str = "agents_0005"
down_revision: Union[str, None] = "agents_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _migrate_flow_payload(value: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    out = copy.deepcopy(value)
    changed = False
    if "skills" in out:
        legacy = out.pop("skills")
        changed = True
        if isinstance(legacy, dict) and len(legacy) > 0:
            existing = out.get("branches")
            has_branches = isinstance(existing, dict) and len(existing) > 0
            if has_branches:
                raise ValueError("flow: одновременно branches и skills")
            out["branches"] = legacy
    return out, changed


def upgrade() -> None:
    conn = op.get_bind()
    for table in ("flows", "flows_versions"):
        rows = conn.execute(sa.text(f"SELECT key, value FROM {table}")).fetchall()
        for row in rows:
            key = row[0]
            value = row[1]
            if not isinstance(value, dict):
                continue
            new_val, changed = _migrate_flow_payload(value)
            if not changed:
                continue
            conn.execute(
                sa.text(f"UPDATE {table} SET value = CAST(:payload AS jsonb) WHERE key = :key"),
                {"payload": json.dumps(new_val, ensure_ascii=False), "key": key},
            )


def downgrade() -> None:
    pass
