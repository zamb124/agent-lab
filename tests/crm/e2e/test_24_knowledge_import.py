"""
E2E импорта базы знаний: реальный TaskIQ worker, S3/MinIO, парсинг файлов, откат.

LLM мокируется только в сценарии mode=graph (mock_llm_redis), как в test_05_ai_analysis.
"""

from __future__ import annotations

import json
import uuid
from io import BytesIO
from pathlib import Path

import fitz
import openpyxl
import pytest
from docx import Document

from tests.crm.knowledge_import_helpers import (
    combined_entity_blob,
    crm_upload_bytes,
    fetch_entity_texts,
    rollback_task,
    wait_task_terminal,
)
from tests.fixtures.crm_test_setup import ensure_entity_type_in_namespace

_META = {"dates_mentioned": [], "places_mentioned": [], "key_topics": []}

pytestmark = [
    pytest.mark.real_taskiq,
    pytest.mark.timeout(120, func_only=True),
]


def _test_namespace(unique_id: str) -> str:
    return f"g_{unique_id}_{uuid.uuid4().hex[:8]}"


def _xlsx_bytes(marker: str) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws["A1"] = marker
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _docx_bytes(marker: str) -> bytes:
    doc = Document()
    doc.add_paragraph(marker)
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _pdf_bytes(tmp_path: Path, marker: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), marker)
    out = tmp_path / "kn_e2e.pdf"
    doc.save(out)
    doc.close()
    return out.read_bytes()


async def _start_notes_import(
    crm_client,
    headers: dict,
    *,
    namespace: str,
    source_text: str | None = None,
    source_file_id: str | None = None,
    source_file_ids: list[str] | None = None,
    split_by_headings: bool = False,
    chunk_max_chars: int = 50_000,
) -> str:
    await _ensure_import_namespace(crm_client, headers, namespace)

    body: dict = {
        "namespace": namespace,
        "mode": "notes_only",
        "split_by_headings": split_by_headings,
        "chunk_max_chars": chunk_max_chars,
    }
    if source_text is not None:
        body["source_text"] = source_text
    if source_file_id is not None:
        body["source_file_id"] = source_file_id
    if source_file_ids is not None:
        body["source_file_ids"] = source_file_ids
    response = await crm_client.post(
        "/crm/api/v1/tasks/knowledge-import",
        json=body,
        headers=headers,
    )
    if response.status_code != 202:
        raise AssertionError(f"start import: {response.status_code} {response.text}")
    payload = response.json()
    task_id = payload.get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        raise AssertionError(f"нет task_id: {payload}")
    return task_id.strip()


async def _ensure_import_namespace(crm_client, headers: dict, namespace: str) -> None:
    create_ns = await crm_client.post(
        "/crm/api/v1/namespaces",
        json={"name": namespace, "template_id": "sales"},
        headers=headers,
    )
    if create_ns.status_code not in (201, 409):
        raise AssertionError(f"create namespace: {create_ns.status_code} {create_ns.text}")
    editability = await crm_client.get(
        f"/crm/api/v1/namespaces/{namespace}/editability",
        headers=headers,
    )
    if editability.status_code != 200:
        raise AssertionError(f"namespace editability: {editability.status_code} {editability.text}")
    allowed = editability.json().get("current_allowed_type_ids") or []
    target_allowed = sorted({*allowed, "note", "meeting", "task"})
    update_ns = await crm_client.put(
        f"/crm/api/v1/namespaces/{namespace}",
        json={"allowed_type_ids": target_allowed},
        headers=headers,
    )
    if update_ns.status_code != 200:
        raise AssertionError(f"namespace update: {update_ns.status_code} {update_ns.text}")
    for system_type in ("note", "meeting", "task"):
        await ensure_entity_type_in_namespace(
            crm_client,
            headers,
            system_type,
            system_type,
            namespace,
        )


async def _assert_blob_then_rollback(
    crm_client,
    headers: dict,
    *,
    task_id: str,
    must_contain: str,
) -> None:
    row = await wait_task_terminal(crm_client, headers, task_id)
    assert row.get("status") == "completed"
    ids = (row.get("data") or {}).get("created_entity_ids") or []
    assert len(ids) >= 1
    blob = combined_entity_blob(await fetch_entity_texts(crm_client, headers, ids))
    assert must_contain in blob
    await rollback_task(crm_client, headers, task_id)
    final = await crm_client.get(
        f"/crm/api/v1/tasks/{task_id}",
        headers=headers,
    )
    assert final.status_code == 200
    assert final.json().get("status") == "rolled_back"
    for eid in ids:
        er = await crm_client.get(f"/crm/api/v1/entities/{eid}", headers=headers)
        assert er.status_code == 404, er.text


class TestKnowledgeImportE2E:
    @pytest.mark.asyncio
    async def test_notes_only_inline_text(
        self, crm_client, crm_worker, unique_id, auth_headers_system
    ) -> None:
        ns = _test_namespace(unique_id)
        marker = f"KN_E2E_INLINE_{unique_id}"
        task_id = await _start_notes_import(
            crm_client,
            auth_headers_system,
            namespace=ns,
            source_text=f"Заголовок\n\n{marker}\n",
        )
        await _assert_blob_then_rollback(
            crm_client,
            auth_headers_system,
            task_id=task_id,
            must_contain=marker,
        )

    @pytest.mark.asyncio
    async def test_notes_only_markdown_file(
        self, crm_client, crm_worker, unique_id, auth_headers_system
    ) -> None:
        ns = _test_namespace(unique_id)
        marker = f"KN_E2E_MD_{unique_id}"
        raw = f"# Раздел\n\n{marker}\n".encode("utf-8")
        fid = await crm_upload_bytes(crm_client, auth_headers_system, f"{unique_id}.md", raw)
        task_id = await _start_notes_import(
            crm_client,
            auth_headers_system,
            namespace=ns,
            source_file_ids=[fid],
        )
        await _assert_blob_then_rollback(
            crm_client,
            auth_headers_system,
            task_id=task_id,
            must_contain=marker,
        )

    @pytest.mark.asyncio
    async def test_notes_only_txt_file(
        self, crm_client, crm_worker, unique_id, auth_headers_system
    ) -> None:
        ns = _test_namespace(unique_id)
        marker = f"KN_E2E_TXT_{unique_id}"
        raw = f"plain\n{marker}\n".encode("utf-8")
        fid = await crm_upload_bytes(crm_client, auth_headers_system, f"{unique_id}.txt", raw)
        task_id = await _start_notes_import(
            crm_client,
            auth_headers_system,
            namespace=ns,
            source_file_id=fid,
        )
        await _assert_blob_then_rollback(
            crm_client,
            auth_headers_system,
            task_id=task_id,
            must_contain=marker,
        )

    @pytest.mark.asyncio
    async def test_notes_only_csv_file(
        self, crm_client, crm_worker, unique_id, auth_headers_system
    ) -> None:
        ns = _test_namespace(unique_id)
        marker = f"KN_E2E_CSV_{unique_id}"
        raw = f"col1,col2\n1,{marker}\n".encode("utf-8")
        fid = await crm_upload_bytes(crm_client, auth_headers_system, f"{unique_id}.csv", raw)
        task_id = await _start_notes_import(
            crm_client,
            auth_headers_system,
            namespace=ns,
            source_file_ids=[fid],
        )
        await _assert_blob_then_rollback(
            crm_client,
            auth_headers_system,
            task_id=task_id,
            must_contain=marker,
        )

    @pytest.mark.asyncio
    async def test_notes_only_xlsx_file(
        self, crm_client, crm_worker, unique_id, auth_headers_system
    ) -> None:
        ns = _test_namespace(unique_id)
        marker = f"KN_E2E_XLSX_{unique_id}"
        raw = _xlsx_bytes(marker)
        fid = await crm_upload_bytes(crm_client, auth_headers_system, f"{unique_id}.xlsx", raw)
        task_id = await _start_notes_import(
            crm_client,
            auth_headers_system,
            namespace=ns,
            source_file_ids=[fid],
        )
        await _assert_blob_then_rollback(
            crm_client,
            auth_headers_system,
            task_id=task_id,
            must_contain=marker,
        )

    @pytest.mark.asyncio
    async def test_notes_only_docx_file(
        self, crm_client, crm_worker, unique_id, auth_headers_system
    ) -> None:
        ns = _test_namespace(unique_id)
        marker = f"KN_E2E_DOCX_{unique_id}"
        raw = _docx_bytes(marker)
        fid = await crm_upload_bytes(crm_client, auth_headers_system, f"{unique_id}.docx", raw)
        task_id = await _start_notes_import(
            crm_client,
            auth_headers_system,
            namespace=ns,
            source_file_ids=[fid],
        )
        await _assert_blob_then_rollback(
            crm_client,
            auth_headers_system,
            task_id=task_id,
            must_contain=marker,
        )

    @pytest.mark.asyncio
    async def test_notes_only_pdf_file(
        self, crm_client, crm_worker, unique_id, auth_headers_system, tmp_path
    ) -> None:
        ns = _test_namespace(unique_id)
        marker = f"KN_E2E_PDF_{unique_id}"
        raw = _pdf_bytes(tmp_path, marker)
        fid = await crm_upload_bytes(crm_client, auth_headers_system, f"{unique_id}.pdf", raw)
        task_id = await _start_notes_import(
            crm_client,
            auth_headers_system,
            namespace=ns,
            source_file_ids=[fid],
        )
        await _assert_blob_then_rollback(
            crm_client,
            auth_headers_system,
            task_id=task_id,
            must_contain=marker,
        )

    @pytest.mark.asyncio
    async def test_notes_only_two_files_and_inline(
        self, crm_client, crm_worker, unique_id, auth_headers_system
    ) -> None:
        ns = _test_namespace(unique_id)
        m1 = f"KN_E2E_M1_{unique_id}"
        m2 = f"KN_E2E_M2_{unique_id}"
        m0 = f"KN_E2E_M0_{unique_id}"
        f1 = await crm_upload_bytes(
            crm_client,
            auth_headers_system,
            f"a_{unique_id}.txt",
            f"file1\n{m1}\n".encode("utf-8"),
        )
        f2 = await crm_upload_bytes(
            crm_client,
            auth_headers_system,
            f"b_{unique_id}.txt",
            f"file2\n{m2}\n".encode("utf-8"),
        )
        task_id = await _start_notes_import(
            crm_client,
            auth_headers_system,
            namespace=ns,
            source_text=f"inline\n{m0}\n",
            source_file_ids=[f1, f2],
        )
        row = await wait_task_terminal(crm_client, auth_headers_system, task_id)
        assert row.get("status") == "completed"
        ids = (row.get("data") or {}).get("created_entity_ids") or []
        blob = combined_entity_blob(await fetch_entity_texts(crm_client, auth_headers_system, ids))
        assert m0 in blob and m1 in blob and m2 in blob
        await rollback_task(crm_client, auth_headers_system, task_id)

    @pytest.mark.asyncio
    async def test_notes_only_split_by_headings_two_notes(
        self, crm_client, crm_worker, unique_id, auth_headers_system
    ) -> None:
        ns = _test_namespace(unique_id)
        a = f"KN_E2E_HA_{unique_id}"
        b = f"KN_E2E_HB_{unique_id}"
        text = f"# Part one\n\n{a}\n\n## Part two\n\n{b}\n"
        task_id = await _start_notes_import(
            crm_client,
            auth_headers_system,
            namespace=ns,
            source_text=text,
            split_by_headings=True,
        )
        row = await wait_task_terminal(crm_client, auth_headers_system, task_id)
        assert (row.get("data") or {}).get("notes_created_count") == 2
        ids = (row.get("data") or {}).get("created_entity_ids") or []
        blob = combined_entity_blob(await fetch_entity_texts(crm_client, auth_headers_system, ids))
        assert a in blob and b in blob
        await rollback_task(crm_client, auth_headers_system, task_id)

    @pytest.mark.asyncio
    async def test_review_list_and_complete_then_rollback(
        self, crm_client, crm_worker, unique_id, auth_headers_system
    ) -> None:
        ns = _test_namespace(unique_id)
        marker = f"KN_E2E_REV_{unique_id}"
        task_id = await _start_notes_import(
            crm_client,
            auth_headers_system,
            namespace=ns,
            source_text=f"text\n{marker}\n",
        )
        row = await wait_task_terminal(crm_client, auth_headers_system, task_id)
        assert row.get("status") == "completed"
        list_r = await crm_client.get(
            f"/crm/api/v1/tasks/{task_id}/created-entities",
            headers=auth_headers_system,
        )
        assert list_r.status_code == 200
        listed = list_r.json()
        assert listed.get("task_id") == task_id
        assert len(listed.get("entities") or []) >= 1
        done = await crm_client.post(
            f"/crm/api/v1/tasks/{task_id}/review-complete",
            headers=auth_headers_system,
        )
        assert done.status_code == 200
        assert (done.json().get("data") or {}).get("review_completed_at") is not None
        await rollback_task(crm_client, auth_headers_system, task_id)

    @pytest.mark.asyncio
    async def test_graph_mode_single_chunk_mock_llm(
        self,
        crm_client,
        crm_worker,
        unique_id,
        auth_headers_system,
        mock_llm_redis,
    ) -> None:
        ns = _test_namespace(unique_id)
        chunk_marker = f"KN_E2E_GRAPH_CHUNK_{unique_id}"
        note_title = f"Заметка граф {unique_id}"
        task_name = f"Задача граф {unique_id}"
        payload = {
            "note": {
                "entity_type": "note",
                "name": note_title,
                "description": f"Описание {chunk_marker}",
            },
            "entities": [
                {
                    "entity_type": "task",
                    "name": task_name,
                    "description": "Задача из импорта графом",
                    "attributes": {"origin": "knowledge_import"},
                },
            ],
            "relationships": [
                {
                    "source_type": "note",
                    "source_name": note_title,
                    "target_type": "task",
                    "target_name": task_name,
                    "relationship_type": "mentions",
                    "weight": 1.0,
                    "confidence": 0.9,
                },
            ],
            "metadata": _META,
        }
        await mock_llm_redis(
            [
                {"type": "text", "content": json.dumps(payload)},
                {"type": "text", "content": json.dumps(payload)},
            ]
        )
        await _ensure_import_namespace(crm_client, auth_headers_system, ns)
        body = {
            "namespace": ns,
            "mode": "graph",
            "source_text": f"Текст для анализа. {chunk_marker}",
            "extract_entity_types": ["task"],
            "split_by_headings": False,
            "chunk_max_chars": 50_000,
        }
        response = await crm_client.post(
            "/crm/api/v1/tasks/knowledge-import",
            json=body,
            headers=auth_headers_system,
        )
        assert response.status_code == 202, response.text
        task_id = response.json()["task_id"]
        row = await wait_task_terminal(
            crm_client,
            auth_headers_system,
            task_id,
        )
        assert row.get("status") == "completed"
        assert int((row.get("data") or {}).get("notes_created_count") or 0) >= 1
        assert int((row.get("data") or {}).get("entities_created_count") or 0) >= 1
        ids = (row.get("data") or {}).get("created_entity_ids") or []
        blob = combined_entity_blob(await fetch_entity_texts(crm_client, auth_headers_system, ids))
        assert chunk_marker in blob
        assert task_name in blob
        await rollback_task(crm_client, auth_headers_system, task_id)

    @pytest.mark.asyncio
    async def test_graph_mode_meeting_stored_as_note_for_notes_ui(
        self,
        crm_client,
        crm_worker,
        unique_id,
        auth_headers_system,
        mock_llm_redis,
    ) -> None:
        ns = _test_namespace(unique_id)
        chunk_marker = f"KN_E2E_MEET_NOTE_{unique_id}"
        note_title = f"Заметка контейнер {unique_id}"
        meeting_name = f"Встреча E2E {unique_id}"
        await mock_llm_redis(
            [
                {
                    "type": "text",
                    "content": json.dumps(
                        {
                            "note": {
                                "entity_type": "note",
                                "name": note_title,
                                "description": f"Текст чанка {chunk_marker}",
                            },
                            "entities": [
                                {
                                    "entity_type": "meeting",
                                    "name": meeting_name,
                                    "description": "Онлайн звонок",
                                    "attributes": {"origin": "knowledge_import"},
                                },
                            ],
                            "relationships": [
                                {
                                    "source_type": "note",
                                    "source_name": note_title,
                                    "target_type": "meeting",
                                    "target_name": meeting_name,
                                    "relationship_type": "mentions",
                                    "weight": 1.0,
                                    "confidence": 0.9,
                                },
                            ],
                            "metadata": _META,
                        }
                    ),
                }
            ]
        )
        await _ensure_import_namespace(crm_client, auth_headers_system, ns)
        body = {
            "namespace": ns,
            "mode": "graph",
            "source_text": f"Контент импорта. {chunk_marker}",
            "extract_entity_types": ["meeting"],
            "split_by_headings": False,
            "chunk_max_chars": 50_000,
        }
        response = await crm_client.post(
            "/crm/api/v1/tasks/knowledge-import",
            json=body,
            headers=auth_headers_system,
        )
        assert response.status_code == 202, response.text
        task_id = response.json()["task_id"]
        row = await wait_task_terminal(
            crm_client,
            auth_headers_system,
            task_id,
        )
        assert row.get("status") == "completed"
        list_r = await crm_client.post(
            "/crm/api/v1/entities/query",
            json={
                "namespace": ns,
                "entity_type": "note",
                "limit": 50,
                "search_mode": "hybrid",
            },
            headers=auth_headers_system,
        )
        assert list_r.status_code == 200, list_r.text
        payload = list_r.json()
        items = payload.get("items", payload) if isinstance(payload, dict) else payload
        assert any(
            e.get("entity_type") == "note"
            and e.get("entity_subtype") in ("meeting", None, "")
            for e in items
        ), items
        await rollback_task(crm_client, auth_headers_system, task_id)
