"""Official fixture pin integrity (no network when VERSION hashes match disk)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from tests.flows.a2a_conformance.helpers.schema import (
    FIXTURES_DIR,
    load_official_json_schema,
    load_official_version,
)


def test_official_fixtures_present_and_hashed() -> None:
    version = load_official_version()
    proto = (FIXTURES_DIR / "a2a.proto").read_bytes()
    schema_bytes = (FIXTURES_DIR / "a2a.json").read_bytes()
    assert version["tag"] == "v1.0.0"
    assert version["commit"]
    assert hashlib.sha256(proto).hexdigest() == version["proto_sha256"]
    assert hashlib.sha256(schema_bytes).hexdigest() == version["json_sha256"]
    schema = load_official_json_schema()
    assert "definitions" in schema
    assert "Part" in schema["definitions"]
    assert "Agent Card" in schema["definitions"]
    examples = Path(FIXTURES_DIR / "examples")
    assert (examples / "send_message_request.json").is_file()
    assert (examples / "part_text.json").is_file()
