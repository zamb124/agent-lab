"""CI gate: MCP branding git bundle (manifest + icon files)."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import NoReturn

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_MANIFEST = _REPO_ROOT / "apps/flows/mcp_branding/manifest.yaml"
_SERVER_ID_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{1,63}$")


def _fail(message: str) -> NoReturn:
    print(f"check_mcp_branding_bundle: {message}", file=sys.stderr)
    raise SystemExit(1)


def check_mcp_branding_bundle(*, manifest_path: Path | None = None) -> None:
    resolved = manifest_path if manifest_path is not None else _DEFAULT_MANIFEST
    if not resolved.is_file():
        _fail(f"manifest not found: {resolved}")

    bundle_dir = resolved.parent
    raw = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        _fail("manifest root must be a mapping")

    default_icon_raw = raw.get("default_icon")
    if not isinstance(default_icon_raw, str):
        _fail("default_icon is required")
    default_icon_name = default_icon_raw.strip()
    if not default_icon_name:
        _fail("default_icon is required")
    default_icon = bundle_dir / default_icon_name
    if not default_icon.is_file():
        _fail(f"default_icon file missing: {default_icon}")

    entries_raw = raw.get("entries")
    if entries_raw is None:
        entries_raw = []
    if not isinstance(entries_raw, list):
        _fail("entries must be a list")

    seen_server_ids: set[str] = set()
    for row in entries_raw:
        if not isinstance(row, dict):
            _fail(f"entry must be a mapping: {row!r}")
        server_id_raw = row.get("server_id")
        file_raw = row.get("file")
        if not isinstance(server_id_raw, str):
            _fail(f"entry server_id is required: {row!r}")
        if not isinstance(file_raw, str):
            _fail(f"entry file is required for {server_id_raw!r}")
        server_id = server_id_raw.strip()
        file_name = file_raw.strip()
        if not server_id:
            _fail(f"entry server_id is required: {row!r}")
        if not file_name:
            _fail(f"entry file is required for {server_id!r}")
        if not _SERVER_ID_PATTERN.match(server_id):
            _fail(f"invalid server_id: {server_id!r}")
        if server_id in seen_server_ids:
            _fail(f"duplicate server_id in manifest: {server_id}")
        seen_server_ids.add(server_id)
        icon_path = bundle_dir / file_name
        if not icon_path.is_file():
            _fail(f"icon file missing for {server_id}: {icon_path}")

    print(f"check_mcp_branding_bundle: OK ({len(seen_server_ids)} entries, default={default_icon.name})")


if __name__ == "__main__":
    check_mcp_branding_bundle()
