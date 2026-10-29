#!/usr/bin/env python3
"""report_ui_kostyli.py — инвентарь отсебятины UI: очередь рекурсивного цикла.

Прогоняет все правила `ui_canon_rules.py` и печатает отчёт:
  --json   reports/ui-kostyli.json (машинная очередь для skill-цикла)
  --md     markdown-таблица по правилам и сервисам
  default  компактная сводка в stdout

Exit code: 0 всегда (это отчёт, не гейт; гейт — check_ui_kit_canon.py).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict

from scripts.gates.frontend.ui_canon_rules import REPO_ROOT, RULES, iter_findings


def collect() -> dict[str, list[tuple[str, str, int, str]]]:
    report: dict[str, list[tuple[str, str, int, str]]] = {}
    for rule in RULES:
        report[rule.rule_id] = [(rel, scope_of(rel), line, text) for _, rel, line, text in iter_findings(rule)]
    return report


def scope_of(rel: str) -> str:
    parts = rel.split("/")
    if parts[0] == "apps" and len(parts) > 2 and parts[2] == "ui":
        return f"apps/{parts[1]}"
    if rel.startswith("core/frontend/static/lib"):
        return "core/lib"
    return parts[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="записать reports/ui-kostyli.json")
    parser.add_argument("--md", action="store_true", help="markdown-таблица")
    args = parser.parse_args()

    rules_by_id = {r.rule_id: r for r in RULES}
    report = collect()

    total = sum(len(v) for v in report.values())
    hard = sum(len(report[r.rule_id]) for r in RULES if r.severity == "hard")

    if args.json:
        out = {
            "totals": {"violations": total, "hard": hard},
            "rules": {
                rid: {
                    "severity": rules_by_id[rid].severity,
                    "fix": rules_by_id[rid].fix,
                    "count": len(items),
                    "files": sorted({rel for rel, _, _, _ in items}),
                    "findings": [{"file": rel, "line": ln, "text": t} for rel, _, ln, t in items],
                }
                for rid, items in report.items()
                if items
            },
        }
        out_path = REPO_ROOT / "reports" / "ui-kostyli.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"report_ui_kostyli: {out_path.relative_to(REPO_ROOT)} ({total} findings)")
        return 0

    if args.md:
        print("| rule | severity | count | files | fix |")
        print("|---|---|---|---|---|")
        for rid, items in sorted(report.items(), key=lambda kv: -len(kv[1])):
            if not items:
                continue
            r = rules_by_id[rid]
            files = sorted({rel for rel, _, _, _ in items})
            print(f"| `{rid}` | {r.severity} | {len(items)} | {len(files)} | {r.fix} |")
        return 0

    print(f"ui-kostyli: {total} findings ({hard} hard)")
    by_scope: dict[str, int] = defaultdict(int)
    for items in report.values():
        for _, scope, _, _ in items:
            by_scope[scope] += 1
    for rid, items in sorted(report.items(), key=lambda kv: -len(kv[1])):
        if items:
            print(f"  {rid}: {len(items)}")
    print("по зонам:")
    for scope, n in sorted(by_scope.items(), key=lambda kv: -kv[1]):
        print(f"  {scope}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
