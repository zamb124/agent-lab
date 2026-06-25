"""Юнит-тесты FileRef helpers и WorkItem variables/attachments."""

from __future__ import annotations

from datetime import datetime, timezone

from core.files.file_attachments import (
    file_ref_ids,
    merge_file_refs,
    minimal_file_refs_from_file_ids,
    parse_file_refs,
)
from core.files.file_ref import FileRef
from core.variables.models import VariableEntry, normalize_variables_map
from core.worktracker.models import SystemActor, WorkItem, WorkItemComment, WorkItemResolution


def _now() -> datetime:
    return datetime.now(timezone.utc)


def test_minimal_file_refs_from_file_ids() -> None:
    refs = minimal_file_refs_from_file_ids(["file_a", "file_b"])
    assert len(refs) == 2
    assert refs[0].file_id == "file_a"
    assert refs[0].original_name == "file_a"
    assert refs[0].content_type == "application/octet-stream"
    assert refs[0].file_size == 0


def test_merge_file_refs_dedupes_by_file_id() -> None:
    first = FileRef(
        file_id="f1",
        original_name="a.pdf",
        content_type="application/pdf",
        file_size=10,
    )
    second = FileRef(
        file_id="f1",
        original_name="b.pdf",
        content_type="application/pdf",
        file_size=20,
    )
    merged = merge_file_refs([first], [second])
    assert len(merged) == 1
    assert merged[0].original_name == "a.pdf"


def test_parse_file_refs_roundtrip() -> None:
    refs = [
        FileRef(
            file_id="f1",
            original_name="doc.txt",
            content_type="text/plain",
            file_size=5,
            url="/frontend/api/v1/files/download/f1",
        )
    ]
    raw = [ref.model_dump(mode="json") for ref in refs]
    restored = parse_file_refs(raw)
    assert len(restored) == 1
    assert restored[0].file_id == "f1"
    assert restored[0].original_name == "doc.txt"
    assert file_ref_ids(restored) == ["f1"]


def test_normalize_variables_map_scalar_and_wrapped() -> None:
    variables = normalize_variables_map(
        {
            "plain": "hello",
            "wrapped": {"value": "secret", "secret": True},
        }
    )
    assert variables["plain"].value == "hello"
    assert variables["plain"].secret is False
    assert variables["wrapped"].value == "secret"
    assert variables["wrapped"].secret is True


def test_work_item_variables_attachments_defaults() -> None:
    item = WorkItem(
        work_item_id="wi_1",
        company_id="company_1",
        title="Task",
        created_by=SystemActor(),
        created_at=_now(),
        updated_at=_now(),
    )
    assert item.variables == {}
    assert item.attachments == []


def test_work_item_resolution_files() -> None:
    file_ref = FileRef(
        file_id="f1",
        original_name="out.pdf",
        content_type="application/pdf",
        file_size=100,
    )
    resolution = WorkItemResolution(text="done", files=[file_ref])
    assert resolution.files[0].file_id == "f1"


def test_work_item_comment_files() -> None:
    file_ref = FileRef(
        file_id="f2",
        original_name="shot.png",
        content_type="image/png",
        file_size=200,
    )
    comment = WorkItemComment(
        comment_id="c1",
        work_item_id="wi_1",
        company_id="company_1",
        author=SystemActor(),
        role="system",
        text="see file",
        files=[file_ref],
        created_at=_now(),
    )
    assert comment.files[0].original_name == "shot.png"


def test_variable_entry_parity_with_flow() -> None:
    entry = VariableEntry(value={"nested": 1}, secret=False, title="T")
    restored = VariableEntry.model_validate(entry.model_dump(mode="json"))
    assert restored.value == {"nested": 1}
    assert restored.title == "T"
