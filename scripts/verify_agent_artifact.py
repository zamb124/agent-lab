#!/usr/bin/env python3
"""CLI: проверка артефакта HumanitecAgent после сборки (CI и локально)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from apps.agent.desktop.artifact_verify import ArtifactVerificationError, verify_artifact
from apps.agent.desktop.build_contract import (
    DESKTOP_ROOT,
    artifact_path,
    load_default_distro_config,
)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify HumanitecAgent build artifact")
    parser.add_argument("--platform", required=True)
    parser.add_argument("--version-sha", required=True)
    parser.add_argument("--artifact-mode", choices=("placeholder", "release"), required=True)
    parser.add_argument("--dist-dir", default=str(DESKTOP_ROOT / "dist"))
    parser.add_argument("--artifact-path", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    dist_dir = Path(str(args.dist_dir))
    distro = load_default_distro_config()
    resolved_path = (
        Path(str(args.artifact_path))
        if str(args.artifact_path)
        else artifact_path(dist_dir, str(args.platform), str(args.version_sha), distro)
    )
    verify_artifact(
        resolved_path,
        platform=str(args.platform),
        version_sha=str(args.version_sha),
        artifact_mode=str(args.artifact_mode),
    )
    print(f"verify_agent_artifact: OK {resolved_path.name}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ArtifactVerificationError as exc:
        print(f"verify_agent_artifact: FAIL {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
