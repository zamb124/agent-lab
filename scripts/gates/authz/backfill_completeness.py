#!/usr/bin/env python3
"""CI gate: every authz tuple helper appears in matching backfill or FGA-only allowlist."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from scripts.gates.kit import REPO_ROOT as _ROOT

_TUPLE_DEF = re.compile(r"^def ([a-z_][a-z0-9_]*)\(", re.M)

# Helpers that have no SQL recovery source — OpenFGA store backup is SoT.
# Also non-tuple validators/helpers that live next to tuples.
_FGA_ONLY_NO_SQL_SOURCE: frozenset[str] = frozenset(
    {
        "assert_viewer_or_editor",
        # Wiki page members (viewer/editor)
        "wiki_page_member_tuple",
        # CRM grants beyond structural owner/namespace
        "crm_grant_tuple",
        # Mail managers/members beyond owner+company
        "mailbox_binding_member_tuple",
        "mailbox_binding_manager_tuple",
        # Document members / company_visible / source (structural owner is SQL)
        "document_catalog_member_tuple",
        "document_catalog_company_viewer_tuple",
        "document_catalog_source_tuple",
        "document_file_member_tuple",
        "document_file_source_tuple",
        # Worktracker queue members
        "work_queue_member_tuple",
        # Flows: owner may be "system" for seeds; group/company viewers are FGA grants
        "flow_owner_tuple",
        "flow_group_viewer_tuple",
        "flow_company_viewer_tuple",
        "flow_branch_group_viewer_tuple",
        "flow_branch_company_viewer_tuple",
        "tool_group_viewer_tuple",
        "tool_company_viewer_tuple",
        # Stock warehouse owner/members are FGA grants (нет owner-колонки в SQL)
        "stock_warehouse_owner_tuple",
        "stock_warehouse_member_tuple",
    }
)


def _tuple_modules() -> list[Path]:
    paths: list[Path] = []
    for pattern in ("apps/*/authz/tuples.py", "core/*/authz/tuples.py"):
        paths.extend(_ROOT.glob(pattern))
    return sorted({p.resolve() for p in paths if p.is_file()})


_EXTRA_BACKFILL: dict[str, str] = {
    "core/documents/authz/tuples.py": "apps/office/authz/backfill.py",
}


def _backfill_text_for(tuples_path: Path) -> str:
    parts: list[str] = []
    sibling = tuples_path.with_name("backfill.py")
    if sibling.is_file():
        parts.append(sibling.read_text(encoding="utf-8"))
    extra = _EXTRA_BACKFILL.get(tuples_path.relative_to(_ROOT).as_posix())
    if extra is not None:
        extra_path = _ROOT / extra
        parts.append(extra_path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def main() -> int:
    errors: list[str] = []
    for path in _tuple_modules():
        text = path.read_text(encoding="utf-8")
        helpers = _TUPLE_DEF.findall(text)
        if not helpers:
            continue
        backfill = _backfill_text_for(path)
        rel = path.relative_to(_ROOT).as_posix()
        for helper in helpers:
            if helper.startswith("_"):
                continue
            if helper in _FGA_ONLY_NO_SQL_SOURCE:
                continue
            if helper not in backfill:
                errors.append(
                    f"{rel}: tuple helper `{helper}` missing from matching backfill "
                    f"(add write or list in FGA_ONLY_NO_SQL_SOURCE)"
                )

    if errors:
        print("check_authz_backfill_completeness FAILED:", file=sys.stderr)
        for item in errors:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("check_authz_backfill_completeness OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
