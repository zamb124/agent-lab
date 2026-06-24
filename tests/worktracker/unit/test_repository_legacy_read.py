"""Legacy resolution file_ids → FileRef при чтении из JSON."""

from __future__ import annotations

from core.files.file_ref import FileRef
from core.types import require_json_object
from core.worktracker.repository import _resolution_from_json


def test_resolution_from_json_legacy_file_ids() -> None:
    raw = require_json_object(
        {
            "text": "done",
            "file_ids": ["legacy_a", "legacy_b"],
            "resolved_by": {"actor_kind": "system"},
        },
        "resolution",
    )
    resolution = _resolution_from_json(raw)
    assert resolution.text == "done"
    assert len(resolution.files) == 2
    assert resolution.files[0].file_id == "legacy_a"
    assert resolution.files[1].file_id == "legacy_b"


def test_resolution_from_json_modern_files() -> None:
    file_ref = FileRef(
        file_id="f1",
        original_name="out.pdf",
        content_type="application/pdf",
        file_size=10,
    )
    raw = require_json_object(
        {
            "text": "ok",
            "files": [file_ref.model_dump(mode="json")],
            "resolved_by": {"actor_kind": "system"},
        },
        "resolution",
    )
    resolution = _resolution_from_json(raw)
    assert resolution.files[0].file_id == "f1"
