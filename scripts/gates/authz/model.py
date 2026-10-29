#!/usr/bin/env python3
"""CI gate: OpenFGA model tests via openfga/cli Docker image."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys

from core.types import parse_json_object
from scripts.gates.kit import REPO_ROOT as _ROOT

_AUTHZ_DIR = _ROOT / "core" / "authz"
_MODEL_FGA = _AUTHZ_DIR / "model.fga"
_MODEL_JSON = _AUTHZ_DIR / "model.json"
_STORE_FILE = _AUTHZ_DIR / "model.fga.yaml"
_CLI_IMAGE = "openfga/cli:latest"


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _assert_model_json_matches_dsl() -> int:
    if not _MODEL_FGA.is_file():
        print(f"check_authz_model FAILED: missing {_MODEL_FGA}", file=sys.stderr)
        return 1
    if not _MODEL_JSON.is_file():
        print(f"check_authz_model FAILED: missing {_MODEL_JSON}", file=sys.stderr)
        return 1
    transform = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{_AUTHZ_DIR}:/authz:ro",
            _CLI_IMAGE,
            "model",
            "transform",
            "--file",
            "/authz/model.fga",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if transform.returncode != 0:
        print(transform.stdout, file=sys.stderr)
        print(transform.stderr, file=sys.stderr)
        print("check_authz_model FAILED: fga model transform", file=sys.stderr)
        return transform.returncode
    transformed = parse_json_object(transform.stdout, "fga.model.transform")
    committed = parse_json_object(
        _MODEL_JSON.read_text(encoding="utf-8"),
        "model.json",
    )
    if _canonical_json(transformed) != _canonical_json(committed):
        print(
            "check_authz_model FAILED: model.json out of sync with model.fga. "
            + "Regenerate: docker run --rm -v core/authz:/authz openfga/cli:latest "
            + "model transform --file /authz/model.fga",
            file=sys.stderr,
        )
        return 1
    return 0


def main() -> int:
    if not _STORE_FILE.is_file():
        print(f"check_authz_model FAILED: missing {_STORE_FILE}", file=sys.stderr)
        return 1
    if shutil.which("docker") is None:
        print("check_authz_model FAILED: docker is required", file=sys.stderr)
        return 1
    drift = _assert_model_json_matches_dsl()
    if drift != 0:
        return drift
    command = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{_AUTHZ_DIR}:/authz:ro",
        _CLI_IMAGE,
        "model",
        "test",
        "--tests",
        "/authz/model.fga.yaml",
    ]
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        print("check_authz_model FAILED", file=sys.stderr)
        return completed.returncode
    print("check_authz_model OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
