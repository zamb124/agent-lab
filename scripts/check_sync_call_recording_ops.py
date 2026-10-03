#!/usr/bin/env python3
"""CI-gate: запись звонка Sync живёт в SyncCallRecordingService."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OPERATIONS = REPO_ROOT / "apps" / "sync" / "realtime" / "operations.py"
HANDLERS = REPO_ROOT / "apps" / "sync" / "realtime" / "handlers.py"
SERVICE = REPO_ROOT / "apps" / "sync" / "services" / "recording_service.py"
OPS = ("op_calls_recording_start", "op_calls_recording_stop")
FORBIDDEN = ("SyncCallRecording", "build_livekit_recording_client", "stop_and_finalize_recording")
HANDLER_FORBIDDEN = {
    "stop_and_finalize_recording",
    "build_livekit_recording_client",
    "normalize_s3_egress_endpoint",
}


def _names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def main() -> int:
    source_text = OPERATIONS.read_text(encoding="utf-8")
    tree = ast.parse(source_text)
    errors: list[str] = []
    found = 0
    for node in tree.body:
        if not isinstance(node, ast.AsyncFunctionDef) or node.name not in OPS:
            continue
        found += 1
        source = ast.get_source_segment(source_text, node)
        if source is None:
            errors.append(f"{node.name}: source missing")
            continue
        if "call_recording_service" not in source:
            errors.append(f"{node.name}: must call call_recording_service")
        for name in FORBIDDEN:
            if name in source:
                errors.append(f"{node.name}: {name} belongs in SyncCallRecordingService")
    if found != len(OPS):
        errors.append(f"recording ops: expected {len(OPS)}, found {found}")
    leaked = HANDLER_FORBIDDEN & _names(HANDLERS)
    for name in sorted(leaked):
        errors.append(f"handlers.py: {name} belongs in SyncCallRecordingService")
    if not SERVICE.is_file():
        errors.append("apps/sync/services/recording_service.py: missing")
    if errors:
        print("check_sync_call_recording_ops: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    print("check_sync_call_recording_ops: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
