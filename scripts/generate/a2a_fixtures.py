#!/usr/bin/env python3
"""Pin / verify official A2A Protocol 1.0 fixtures (proto + JSON Schema).

Source of truth: a2aproject/A2A release tag (default v1.0.0).
JSON Schema artifact: https://a2a-protocol.org/<tag>/spec/a2a.json

Usage:
  uv run python -m scripts.generate.a2a_fixtures                 # download + write
  uv run python -m scripts.generate.a2a_fixtures --check         # VERSION + sha на диске
  uv run python -m scripts.generate.a2a_fixtures --check-remote  # то же + сверка с GitHub/docs
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = REPO_ROOT / "tests" / "flows" / "a2a_conformance" / "fixtures" / "official"

DEFAULT_TAG = "v1.0.0"
DEFAULT_COMMIT = "173695755607e884aa9acf8ce4feed90e32727a1"
PROTO_PATH_IN_REPO = "specification/a2a.proto"


def _http_get(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "agent-lab-a2a-fixture-pin/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} for {url}") from exc


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _proto_url(commit: str) -> str:
    return f"https://raw.githubusercontent.com/a2aproject/A2A/{commit}/{PROTO_PATH_IN_REPO}"


def _json_url(tag: str) -> str:
    # Docs site uses tag without leading 'v' in some paths; v1.0.0 works as folder.
    return f"https://a2a-protocol.org/{tag}/spec/a2a.json"


def _version_text(*, tag: str, commit: str, proto_sha: str, json_sha: str) -> str:
    return (
        f"tag={tag}\n"
        f"commit={commit}\n"
        f"protocol_version=1.0\n"
        f"proto_source={_proto_url(commit)}\n"
        f"json_source={_json_url(tag)}\n"
        f"proto_sha256={proto_sha}\n"
        f"json_sha256={json_sha}\n"
    )


def _parse_version_file(text: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        parsed[key] = value
    return parsed


def pin(*, tag: str, commit: str) -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    (FIXTURES_DIR / "examples").mkdir(parents=True, exist_ok=True)

    proto_bytes = _http_get(_proto_url(commit))
    json_bytes = _http_get(_json_url(tag))
    # Fail closed: JSON must parse.
    json.loads(json_bytes.decode("utf-8"))

    proto_sha = _sha256(proto_bytes)
    json_sha = _sha256(json_bytes)

    (FIXTURES_DIR / "a2a.proto").write_bytes(proto_bytes)
    (FIXTURES_DIR / "a2a.json").write_bytes(json_bytes)
    (FIXTURES_DIR / "VERSION").write_text(
        _version_text(tag=tag, commit=commit, proto_sha=proto_sha, json_sha=json_sha),
        encoding="utf-8",
    )
    print(f"Pinned A2A fixtures to {FIXTURES_DIR}")
    print(f"  tag={tag} commit={commit}")
    print(f"  proto_sha256={proto_sha}")
    print(f"  json_sha256={json_sha}")


def check(*, tag: str, commit: str) -> int:
    """Целостность pin на диске. Сеть не нужна: commit в VERSION неизменяем."""
    version_path = FIXTURES_DIR / "VERSION"
    proto_path = FIXTURES_DIR / "a2a.proto"
    json_path = FIXTURES_DIR / "a2a.json"
    for path in (version_path, proto_path, json_path):
        if not path.is_file():
            print(f"FAIL: missing fixture file {path}", file=sys.stderr)
            return 1

    local = _parse_version_file(version_path.read_text(encoding="utf-8"))
    for key, expected in (
        ("tag", tag),
        ("commit", commit),
        ("protocol_version", "1.0"),
    ):
        actual = local.get(key)
        if actual != expected:
            print(f"FAIL: VERSION {key}={actual!r}, expected {expected!r}", file=sys.stderr)
            return 1

    local_proto = proto_path.read_bytes()
    local_json = json_path.read_bytes()
    local_proto_sha = _sha256(local_proto)
    local_json_sha = _sha256(local_json)

    if local.get("proto_sha256") != local_proto_sha:
        print("FAIL: VERSION proto_sha256 does not match a2a.proto on disk", file=sys.stderr)
        return 1
    if local.get("json_sha256") != local_json_sha:
        print("FAIL: VERSION json_sha256 does not match a2a.json on disk", file=sys.stderr)
        return 1

    print(f"OK: A2A fixtures match pin tag={tag} commit={commit}")
    return 0


def check_remote(*, tag: str, commit: str) -> int:
    """Локальный pin + сверка с official proto/JSON. HTTP-ошибка (включая 429) — FAIL."""
    local_status = check(tag=tag, commit=commit)
    if local_status != 0:
        return local_status

    proto_path = FIXTURES_DIR / "a2a.proto"
    json_path = FIXTURES_DIR / "a2a.json"
    local_proto_sha = _sha256(proto_path.read_bytes())
    local_json_sha = _sha256(json_path.read_bytes())

    remote_proto = _http_get(_proto_url(commit))
    remote_json = _http_get(_json_url(tag))
    if _sha256(remote_proto) != local_proto_sha:
        print("FAIL: a2a.proto drift vs remote pin", file=sys.stderr)
        return 1
    if _sha256(remote_json) != local_json_sha:
        print("FAIL: a2a.json drift vs remote pin", file=sys.stderr)
        return 1

    print(f"OK: A2A fixtures match remote tag={tag} commit={commit}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify VERSION + sha256 on disk (no network)",
    )
    parser.add_argument(
        "--check-remote",
        action="store_true",
        help="Verify local pin and compare with official remote artifacts",
    )
    parser.add_argument("--tag", default=DEFAULT_TAG)
    parser.add_argument("--commit", default=DEFAULT_COMMIT)
    args = parser.parse_args()
    if args.check and args.check_remote:
        print("FAIL: задайте либо --check, либо --check-remote", file=sys.stderr)
        return 1
    if args.check:
        return check(tag=args.tag, commit=args.commit)
    if args.check_remote:
        return check_remote(tag=args.tag, commit=args.commit)
    pin(tag=args.tag, commit=args.commit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
