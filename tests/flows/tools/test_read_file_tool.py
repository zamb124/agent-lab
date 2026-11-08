"""Тесты встроенного tool read_file (через capability files.read)."""

from __future__ import annotations

import pytest

from apps.flows.src.state import ExecutionState
from apps.flows.tools.files.files import read_file
from core.context import get_context, set_context
from core.files.file_ref import FileRef
from core.models.identity_models import User
from core.types import require_json_array, require_json_object
from tests.core.files.corpus.e2e_helpers import execution_state_for_files
from tests.core.files.corpus.manifest import POSITIVE
from tests.core.files.corpus.read_helpers import store_corpus_in_files_service
from tests.fixtures.s3 import require_s3_configured

_TEXT = "fake-text.txt"
_EMBEDDED_PDF = "pdf/embedded-images.pdf"


def _bind_persisted_user(user_id: str) -> None:
    """Gateway build_context грузит User из БД; tool conftest ставит ephemeral u1."""
    context = get_context()
    if context is None:
        raise RuntimeError("test context missing")
    user = User(user_id=user_id, name="System")
    _ = set_context(
        context.model_copy(
            update={
                "user": user,
                "metadata": {**context.metadata, "user_id": user_id},
            }
        )
    )


def test_read_file_tool_metadata() -> None:
    assert read_file.name == "read_file"
    assert "read_file" in read_file.description or "Читает" in read_file.description
    params = read_file.parameters
    props = require_json_object(params.get("properties", {}), "read_file.parameters.properties")
    assert "names" in props


@pytest.mark.asyncio
@pytest.mark.timeout(180)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_read_file_via_gateway_txt(
    frontend_di,
    unique_id: str,
    system_user_id: str,
) -> None:
    require_s3_configured()
    _bind_persisted_user(system_user_id)
    entry = next(e for e in POSITIVE if e.relative_path == _TEXT)
    file_ref = await store_corpus_in_files_service(frontend_di, entry, unique_id=unique_id)
    state = execution_state_for_files(files=[file_ref], user_id=system_user_id)
    result = require_json_object(
        await read_file.run({"names": [file_ref.original_name]}, state),
        "read_file.result",
    )
    assert result["success"] is True
    assert result["tool"] == "read_file"
    files = require_json_array(result["files"], "read_file.result.files")
    file_result = require_json_object(files[0], "read_file.result.files[0]")
    assert file_result["success"] is True
    assert file_result["file_id"] == file_ref.file_id
    results = require_json_array(file_result["results"], "read_file.result.files[0].results")
    page = require_json_object(results[0], "read_file.result.files[0].results[0]")
    assert isinstance(page["result"], str) and page["result"].strip()


@pytest.mark.asyncio
@pytest.mark.timeout(120)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_read_file_missing_name_error_in_envelope(
    frontend_di,
    unique_id: str,
    system_user_id: str,
) -> None:
    require_s3_configured()
    _bind_persisted_user(system_user_id)
    entry = next(e for e in POSITIVE if e.relative_path == _TEXT)
    file_ref = await store_corpus_in_files_service(frontend_di, entry, unique_id=unique_id)
    state = execution_state_for_files(files=[file_ref], user_id=system_user_id)
    result = require_json_object(
        await read_file.run(
            {"names": ["definitely-missing.txt", file_ref.original_name]},
            state,
        ),
        "read_file.result",
    )
    assert result["success"] is True
    files = require_json_array(result["files"], "files")
    missing = require_json_object(files[0], "files[0]")
    found = require_json_object(files[1], "files[1]")
    assert missing["success"] is False
    assert missing["stop_reason"] == "error"
    assert found["success"] is True


@pytest.mark.asyncio
@pytest.mark.timeout(180)
@pytest.mark.usefixtures("file_reader_billing_service")
async def test_read_file_nested_refs_upsert_into_state(
    frontend_di,
    unique_id: str,
    system_user_id: str,
) -> None:
    require_s3_configured()
    _bind_persisted_user(system_user_id)
    entry = next(e for e in POSITIVE if e.relative_path == _EMBEDDED_PDF)
    file_ref = await store_corpus_in_files_service(frontend_di, entry, unique_id=unique_id)
    state = execution_state_for_files(files=[file_ref], user_id=system_user_id)
    result = require_json_object(
        await read_file.run(
            {
                "names": [file_ref.original_name],
                "nested_mode": "refs",
                "recursive": False,
            },
            state,
        ),
        "read_file.result",
    )
    assert result["success"] is True
    file_result = require_json_object(
        require_json_array(result["files"], "files")[0],
        "files[0]",
    )
    nested = require_json_array(file_result["nested"], "nested")
    assert nested
    nested_ids = {
        str(require_json_object(item, "nested[]")["file_id"])
        for item in nested
        if isinstance(require_json_object(item, "nested[]").get("file_id"), str)
        and str(require_json_object(item, "nested[]")["file_id"]).strip()
    }
    assert nested_ids
    state_ids = {item.file_id for item in state.files if item.file_id}
    assert nested_ids <= state_ids


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_read_file_requires_persisted_file_id() -> None:
    state = ExecutionState.create(
        task_id="t1",
        context_id="c1",
        user_id="u1",
        session_id="flow:c1",
        files=[
            FileRef(
                original_name="local-only.txt",
                url="/tmp/local-only.txt",
                content_type="text/plain",
                file_size=5,
            )
        ],
    )
    with pytest.raises(ValueError, match="file_id"):
        _ = await read_file.run({"names": ["local-only.txt"]}, state)
