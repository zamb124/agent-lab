"""Zero-reference gate for Flow UI hard cut (plan §27.4)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "legacy chat settings",
        re.compile(r"FlowChatSettings|EmbedChatPolicyOverride|resolve_effective_flow_chat"),
    ),
        (
            "legacy chat profile/runtime",
            re.compile(
                r"chat_override|chat-profile|platform-chat|a2a-chat-runtime|"
                r"lib/chat/|@platform/lib/chat"
            ),
        ),    (
        "legacy ui_event channel",
        re.compile(
            r"ui_events_pending|PendingUIEvent|push_ui_event|emit_ui_event|"
            r"artifact\.name\s*===\s*['\"]ui_event['\"]"
        ),
    ),
    (
        "legacy humanitec a2ui catalog",
        re.compile(r"humanitec\.ai/a2ui|supportedCatalogIds.*humanitec", re.IGNORECASE),
    ),
]

# Intentional exceptions: CDN shim path + migration fixtures.
ALLOWLIST_PREFIXES = (
    "core/frontend/static/lib/embed-chat/",
    "A2A_FLOW_UI_IMPLEMENTATION_PLAN.md",
    "core/models/flow_interface_migration.py",
    "migrations/",
    "scripts/migrate_flow_interface_json.py",
    "scripts/check_flow_ui_hard_cut.py",
    "scripts/check_platform_events_canon.py",
    "core/state/execution_state.py",  # FORBIDDEN_* registry still names deleted fields
    "core/i18n/generated/",  # regenerated from translations
    "tests/core/models/test_flow_interface_migration.py",  # fixtures exercise legacy keys → new schema
)

ALLOWLIST_SUBSTRINGS = (
    ".cursor/rules/",  # rules may mention deleted names as bans
)


def _iter_files() -> list[Path]:
    roots = [
        ROOT / "apps",
        ROOT / "core",
        ROOT / "tests",
        ROOT / ".cursor" / "rules",
        ROOT / "docs" / "openapi",
        ROOT / "scripts",
    ]
    files: list[Path] = []
    skip = {"node_modules", ".venv", "dist", "vendor", "__pycache__"}
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in skip for part in path.parts):
                continue
            if path.suffix not in {".py", ".js", ".ts", ".mdc", ".json", ".md", ".sh"}:
                continue
            files.append(path)
    return files


def _allowed(rel: str) -> bool:
    if any(rel.startswith(prefix) for prefix in ALLOWLIST_PREFIXES):
        return True
    if any(token in rel for token in ALLOWLIST_SUBSTRINGS):
        return True
    return False


def main() -> int:
    # Strict mode for apps + core production code; tests/rules listed but not fail-closed yet
    # once browser suite is rewritten, drop tests/ from ALLOWLIST_SUBSTRINGS.
    failures: list[str] = []
    for path in _iter_files():
        rel = path.relative_to(ROOT).as_posix()
        if _allowed(rel):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in PATTERNS:
            if pattern.search(text):
                failures.append(f"{rel}: {label}")
                break

    chat_dir = ROOT / "core/frontend/static/lib/chat"
    if chat_dir.exists():
        failures.append("core/frontend/static/lib/chat/: directory must be deleted (CDN shim is embed-chat/)")

    if failures:
        print("Flow UI hard-cut gate failed:", file=sys.stderr)
        for item in failures:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("Flow UI hard-cut gate OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
