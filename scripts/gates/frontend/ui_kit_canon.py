#!/usr/bin/env python3
"""check_ui_kit_canon.py — ratchet-гейт UI-канона: hard-нарушения не растут.

Счётчики hard-правил из `ui_canon_rules.py` сравниваются с baseline
`scripts/gates/frontend/ui_canon_baseline.json`. Рост — FAIL. Снижение — подсказка `--update`.
Soft-правила гейт не считает — они живут в `report_ui_kostyli.py`.
"""

from __future__ import annotations

import argparse
import json
import sys

from scripts.gates.frontend.ui_canon_rules import REPO_ROOT, RULES, iter_findings

BASELINE_PATH = REPO_ROOT / "scripts" / "gates" / "frontend" / "ui_canon_baseline.json"


def collect_counts() -> dict[str, int]:
    return {
        rule.rule_id: len(iter_findings(rule))
        for rule in RULES
        if rule.severity == "hard"
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true", help="зафиксировать текущие счётчики как baseline")
    parser.add_argument("--verbose", action="store_true", help="печатать каждое нарушение сверх baseline")
    args = parser.parse_args()

    counts = collect_counts()
    if args.update or not BASELINE_PATH.exists():
        BASELINE_PATH.write_text(json.dumps(counts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"check_ui_kit_canon: baseline записан ({len(counts)} правил)")
        return 0

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    rules_by_id = {r.rule_id: r for r in RULES}
    failures: list[str] = []
    improvements: list[str] = []
    for rule_id, current in counts.items():
        allowed = baseline.get(rule_id)
        if not isinstance(allowed, int):
            failures.append(f"{rule_id}: нет в baseline — запусти --update")
            continue
        if current > allowed:
            failures.append(f"{rule_id}: {current} > {allowed} — {rules_by_id[rule_id].fix}")
        elif current < allowed:
            improvements.append(f"{rule_id}: {current} < {allowed}")
    if failures:
        print("check_ui_kit_canon: FAIL — нарушения канона выросли:")
        for line in failures:
            print(f"  {line}")
        if args.verbose:
            for rule_id, current in counts.items():
                allowed = baseline.get(rule_id, 0)
                if current <= allowed:
                    continue
                for _, rel, ln, text in iter_findings(rules_by_id[rule_id]):
                    print(f"    {rel}:{ln}: {text}")
        return 1
    if improvements:
        print("check_ui_kit_canon: долг снизился, зафиксируй `--update`:")
        for line in improvements:
            print(f"  {line}")
    print(f"check_ui_kit_canon: OK ({len(counts)} hard-правил)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
