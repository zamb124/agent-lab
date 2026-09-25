"""Исторический resolution.file_ids становится files при чтении JSON."""

from __future__ import annotations

from core.files.file_ref import FileRef
from core.worktracker.models import WorkItemResolution


def test_resolution_legacy_file_ids() -> None:
    resolution = WorkItemResolution.model_validate(
        {
            "text": "done",
            "file_ids": ["legacy_a", "legacy_b"],
            "resolved_by": {"actor_kind": "system"},
        }
    )
    assert resolution.text == "done"
    assert len(resolution.files) == 2
    assert resolution.files[0].file_id == "legacy_a"
    assert resolution.files[1].file_id == "legacy_b"


def test_resolution_modern_files() -> None:
    file_ref = FileRef(
        file_id="f1",
        original_name="out.pdf",
        content_type="application/pdf",
        file_size=10,
    )
    resolution = WorkItemResolution.model_validate(
        {
            "text": "ok",
            "files": [file_ref.model_dump(mode="json")],
            "resolved_by": {"actor_kind": "system"},
        }
    )
    assert resolution.files[0].file_id == "f1"
