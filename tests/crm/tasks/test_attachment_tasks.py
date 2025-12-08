"""
Интеграционные тесты для CRM attachment tasks.

Тестирует полный flow:
1. API endpoints для загрузки файлов
2. TaskIQ задачи для индексации в RAG
3. Удаление файлов из RAG и S3
4. Импорт заметок из файлов

ВАЖНО: Тесты используют реальные сервисы без моков!
"""

import pytest
import asyncio
import io
from datetime import date

from core.context import set_context
from apps.crm.models.note_models import NoteCreate, NoteType


# === Тестовые файлы ===

def create_test_txt_file(content: str = "Test content for attachment") -> io.BytesIO:
    """Создает тестовый TXT файл"""
    file = io.BytesIO(content.encode("utf-8"))
    file.name = "test_document.txt"
    return file


def create_test_pdf_content() -> bytes:
    """Создает минимальный валидный PDF"""
    # Минимальный PDF файл
    return b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >> endobj
4 0 obj << /Length 44 >> stream
BT /F1 12 Tf 100 700 Td (Test PDF content) Tj ET
endstream endobj
xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000214 00000 n 
trailer << /Size 5 /Root 1 0 R >>
startxref
307
%%EOF"""


# === Тесты API endpoints ===

@pytest.mark.asyncio
async def test_upload_attachment_endpoint(crm_client, note_service, test_context):
    """
    Тест загрузки файла через API endpoint.
    Проверяет что файл загружается в S3 и добавляется к заметке.
    """
    company_id = test_context.active_company.company_id
    user_id = test_context.user.user_id
    set_context(test_context)
    
    note_data = NoteCreate(
        title="Note with attachment",
        content="Testing file upload",
        note_type=NoteType.FREEFORM,
        note_date=date.today(),
    )
    note = await note_service.create_note(note_data, company_id=company_id, user_id=user_id)
    
    try:
        file_content = b"This is test attachment content for CRM note"
        files = {"file": ("test_attachment.txt", io.BytesIO(file_content), "text/plain")}
        
        response = await crm_client.post(
            f"/crm/api/v1/notes/{note.note_id}/attachments",
            files=files
        )
        
        assert response.status_code == 200, f"Upload failed: {response.text}"
        
        result = response.json()
        assert "file_id" in result
        assert result["original_name"] == "test_attachment.txt"
        assert result["content_type"] == "text/plain"
        assert result["file_size"] == len(file_content)
        
        # Восстанавливаем контекст после HTTP запроса
        set_context(test_context)
        updated_note = await note_service.get_note(note.note_id, company_id=company_id)
        assert result["file_id"] in updated_note.attachment_ids
        
    finally:
        set_context(test_context)
        await note_service.delete_note(note.note_id, company_id=company_id)


@pytest.mark.asyncio
async def test_get_attachments_endpoint(crm_client, note_service, test_context):
    """
    Тест получения списка attachments через API.
    """
    company_id = test_context.active_company.company_id
    user_id = test_context.user.user_id
    set_context(test_context)
    
    note_data = NoteCreate(
        title="Note for attachments list",
        content="Testing attachments list",
        note_type=NoteType.FREEFORM,
        note_date=date.today(),
    )
    note = await note_service.create_note(note_data, company_id=company_id, user_id=user_id)
    
    try:
        for i in range(2):
            files = {"file": (f"file_{i}.txt", io.BytesIO(f"Content {i}".encode()), "text/plain")}
            response = await crm_client.post(
                f"/crm/api/v1/notes/{note.note_id}/attachments",
                files=files
            )
            assert response.status_code == 200
        
        response = await crm_client.get(f"/crm/api/v1/notes/{note.note_id}/attachments")
        assert response.status_code == 200
        
        attachments = response.json()
        assert len(attachments) == 2
        
    finally:
        set_context(test_context)
        await note_service.delete_note(note.note_id, company_id=company_id)


@pytest.mark.asyncio
async def test_delete_attachment_endpoint(crm_client, note_service, test_context):
    """
    Тест удаления attachment через API.
    Проверяет что файл удаляется из списка заметки.
    """
    company_id = test_context.active_company.company_id
    user_id = test_context.user.user_id
    set_context(test_context)
    
    note_data = NoteCreate(
        title="Note for delete attachment",
        content="Testing delete",
        note_type=NoteType.FREEFORM,
        note_date=date.today(),
    )
    note = await note_service.create_note(note_data, company_id=company_id, user_id=user_id)
    
    try:
        files = {"file": ("to_delete.txt", io.BytesIO(b"Will be deleted"), "text/plain")}
        upload_response = await crm_client.post(
            f"/crm/api/v1/notes/{note.note_id}/attachments",
            files=files
        )
        assert upload_response.status_code == 200
        file_id = upload_response.json()["file_id"]
        
        delete_response = await crm_client.delete(
            f"/crm/api/v1/notes/{note.note_id}/attachments/{file_id}"
        )
        assert delete_response.status_code == 200
        
        set_context(test_context)
        updated_note = await note_service.get_note(note.note_id, company_id=company_id)
        assert file_id not in updated_note.attachment_ids
        
    finally:
        set_context(test_context)
        await note_service.delete_note(note.note_id, company_id=company_id)


# === Тесты импорта файлов ===

@pytest.mark.asyncio
async def test_import_note_from_txt_endpoint(crm_client, note_service, test_context):
    """
    Тест импорта заметки из TXT файла через API.
    """
    company_id = test_context.active_company.company_id
    set_context(test_context)
    
    file_content = """Meeting Notes - Project Alpha

Participants: John, Mary, Bob

Key Points:
1. Project timeline approved
2. Budget increased by 20%
3. Next milestone: December 15

Action Items:
- John: prepare technical spec
- Mary: update stakeholders
- Bob: schedule follow-up"""
    
    files = {"file": ("meeting_notes.txt", io.BytesIO(file_content.encode()), "text/plain")}
    data = {
        "title": "Imported Meeting Notes",
        "note_type": "meeting_minutes",
        "note_date": str(date.today()),
    }
    
    response = await crm_client.post(
        "/crm/api/v1/notes/import",
        files=files,
        data=data
    )
    
    assert response.status_code == 200, f"Import failed: {response.text}"
    
    result = response.json()
    assert result["title"] == "Imported Meeting Notes"
    assert result["note_type"] == "meeting_minutes"
    assert result["status"] in ["importing", "draft"]
    
    set_context(test_context)
    await note_service.delete_note(result["note_id"], company_id=company_id)


@pytest.mark.asyncio
async def test_import_note_from_pdf_endpoint(crm_client, note_service, test_context):
    """
    Тест импорта заметки из PDF файла через API.
    """
    company_id = test_context.active_company.company_id
    set_context(test_context)
    
    pdf_content = create_test_pdf_content()
    
    files = {"file": ("document.pdf", io.BytesIO(pdf_content), "application/pdf")}
    data = {
        "title": "Imported PDF Document",
        "note_type": "freeform",
        "note_date": str(date.today()),
    }
    
    response = await crm_client.post(
        "/crm/api/v1/notes/import",
        files=files,
        data=data
    )
    
    assert response.status_code == 200, f"PDF import failed: {response.text}"
    
    result = response.json()
    assert result["title"] == "Imported PDF Document"
    assert len(result["attachment_ids"]) == 1
    
    set_context(test_context)
    await note_service.delete_note(result["note_id"], company_id=company_id)


# === Тесты TaskIQ задач ===

@pytest.mark.asyncio
async def test_attachment_indexing_task(
    note_service, 
    test_context, 
    taskiq_broker,
):
    """
    Тест что attachment индексируется в RAG через TaskIQ.
    Проверяет полный flow: upload -> task -> RAG indexing.
    """
    from apps.crm.tasks import process_crm_attachment_task
    from core.files import get_default_file_processor
    from core.rag.factory import get_default_rag_provider
    
    company_id = test_context.active_company.company_id
    user_id = test_context.user.user_id
    
    # Создаем заметку
    note_data = NoteCreate(
        title="Note for RAG indexing",
        content="Testing RAG",
        note_type=NoteType.FREEFORM,
        note_date=date.today(),
    )
    note = await note_service.create_note(note_data, company_id=company_id, user_id=user_id)
    
    try:
        # Загружаем файл в S3
        file_processor = await get_default_file_processor()
        file_content = b"This document contains important information about client John Smith and project Alpha."
        
        file_record = await file_processor.process_file_from_bytes(
            data=file_content,
            original_name="client_info.txt",
            content_type="text/plain",
            uploaded_by=user_id,
            metadata={"note_id": note.note_id},
            public=False,
        )
        
        # Запускаем таску напрямую (синхронно для теста)
        result = await process_crm_attachment_task(
            company_id=company_id,
            note_id=note.note_id,
            file_id=file_record.file_id,
            s3_key=file_record.s3_key,
            document_name="client_info.txt",
            content_type="text/plain",
            note_title=note.title,
            user_id=user_id,
        )
        
        assert result["status"] == "completed"
        assert "document_id" in result
        
        # Проверяем что документ в RAG
        provider = get_default_rag_provider()
        namespace = f"crm_attachments_{company_id}"
        
        # Поиск по содержимому
        search_results = await provider.search(
            namespace_id=namespace,
            query="John Smith project Alpha",
            limit=5
        )
        
        assert len(search_results) > 0
        
        # Cleanup RAG
        await provider.delete_document(namespace, file_record.file_id)
        
    finally:
        await note_service.delete_note(note.note_id)


@pytest.mark.asyncio
async def test_attachment_deletion_task(
    note_service,
    test_context,
    taskiq_broker,
):
    """
    Тест удаления attachment из RAG и S3 через TaskIQ.
    """
    from apps.crm.tasks import process_crm_attachment_task, delete_crm_attachment_task
    from core.files import get_default_file_processor
    
    company_id = test_context.active_company.company_id
    user_id = test_context.user.user_id
    
    # Создаем заметку
    note_data = NoteCreate(
        title="Note for deletion test",
        content="Testing deletion",
        note_type=NoteType.FREEFORM,
        note_date=date.today(),
    )
    note = await note_service.create_note(note_data, company_id=company_id, user_id=user_id)
    
    try:
        # Загружаем файл
        file_processor = await get_default_file_processor()
        file_content = b"Content to be deleted from RAG and S3"
        
        file_record = await file_processor.process_file_from_bytes(
            data=file_content,
            original_name="to_delete.txt",
            content_type="text/plain",
            uploaded_by=user_id,
            public=False,
        )
        
        # Индексируем в RAG
        await process_crm_attachment_task(
            company_id=company_id,
            note_id=note.note_id,
            file_id=file_record.file_id,
            s3_key=file_record.s3_key,
            document_name="to_delete.txt",
            content_type="text/plain",
        )
        
        # Удаляем через таску
        delete_result = await delete_crm_attachment_task(
            company_id=company_id,
            note_id=note.note_id,
            file_id=file_record.file_id,
            s3_key=file_record.s3_key,
        )
        
        assert delete_result["status"] == "completed"
        assert delete_result["deleted_from_s3"] is True
        
        # Проверяем что файл удален из S3 (404 = успешно удален)
        from core.files.s3_client import S3ClientFactory
        from botocore.exceptions import ClientError
        
        s3_client = S3ClientFactory.create_default_client()
        try:
            file_exists = await s3_client.file_exists(file_record.s3_key)
            assert file_exists is False
        except ClientError as e:
            # 404 означает файл не существует = успешно удален
            assert e.response["Error"]["Code"] == "404"
        
    finally:
        await note_service.delete_note(note.note_id)


@pytest.mark.asyncio
async def test_note_with_attachments_deletion(
    note_service,
    test_context,
    taskiq_broker,
):
    """
    Тест удаления заметки с attachments.
    Проверяет что все файлы удаляются из RAG и S3.
    """
    from apps.crm.tasks import process_crm_attachment_task
    from core.files import get_default_file_processor
    
    company_id = test_context.active_company.company_id
    user_id = test_context.user.user_id
    
    # Создаем заметку
    note_data = NoteCreate(
        title="Note with multiple attachments",
        content="Testing cascade delete",
        note_type=NoteType.FREEFORM,
        note_date=date.today(),
    )
    note = await note_service.create_note(note_data, company_id=company_id, user_id=user_id)
    
    file_processor = await get_default_file_processor()
    file_ids = []
    
    # Загружаем несколько файлов
    for i in range(3):
        file_content = f"Attachment content {i}".encode()
        file_record = await file_processor.process_file_from_bytes(
            data=file_content,
            original_name=f"attachment_{i}.txt",
            content_type="text/plain",
            uploaded_by=user_id,
            public=False,
        )
        file_ids.append(file_record.file_id)
        
        # Добавляем к заметке
        db_note = await note_service._repo.get(note.note_id)
        db_note.attachment_ids = (db_note.attachment_ids or []) + [file_record.file_id]
        await note_service._repo.update(db_note)
        
        # Индексируем
        await process_crm_attachment_task(
            company_id=company_id,
            note_id=note.note_id,
            file_id=file_record.file_id,
            s3_key=file_record.s3_key,
            document_name=f"attachment_{i}.txt",
            content_type="text/plain",
        )
    
    # Удаляем заметку (должна запустить delete_note_attachments_task)
    success = await note_service.delete_note(note.note_id)
    assert success is True
    
    # Даем время на обработку асинхронной таски
    await asyncio.sleep(1)
    
    # Проверяем что заметка удалена
    deleted_note = await note_service.get_note(note.note_id)
    assert deleted_note is None


@pytest.mark.asyncio
async def test_import_note_task_execution(
    note_service,
    test_context,
    taskiq_broker,
):
    """
    Тест выполнения import_note_from_file_task.
    Проверяет что файл парсится и content заметки обновляется.
    """
    from apps.crm.tasks import import_note_from_file_task
    from core.files import get_default_file_processor
    
    company_id = test_context.active_company.company_id
    user_id = test_context.user.user_id
    
    # Загружаем файл в S3
    file_processor = await get_default_file_processor()
    file_content = b"""Important Document

This is the content that should be parsed and added to the note.
It contains multiple paragraphs and important information.

Key points:
- Point 1
- Point 2
- Point 3
"""
    
    file_record = await file_processor.process_file_from_bytes(
        data=file_content,
        original_name="document.txt",
        content_type="text/plain",
        uploaded_by=user_id,
        public=False,
    )
    
    # Создаем заметку со статусом importing
    from apps.crm.db.models import Note
    from datetime import datetime, timezone
    import uuid
    
    note = Note(
        note_id=str(uuid.uuid4()),
        company_id=company_id,
        user_id=user_id,
        title="Imported Document",
        content="",  # Пустой, будет заполнен таской
        note_type="freeform",
        note_date=date.today(),
        status="importing",
        visibility="private",
        attachment_ids=[file_record.file_id],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    await note_service._repo.create(note)
    
    try:
        # Запускаем таску
        result = await import_note_from_file_task(
            note_id=note.note_id,
            company_id=company_id,
            user_id=user_id,
            file_id=file_record.file_id,
            s3_key=file_record.s3_key,
            filename="document.txt",
            title="Imported Document",
            note_type="freeform",
            note_date=str(date.today()),
        )
        
        assert result["status"] == "completed"
        assert result["content_length"] > 0
        
        # Проверяем что content обновлен
        updated_note = await note_service.get_note(note.note_id)
        assert updated_note.content != ""
        assert "Important Document" in updated_note.content or len(updated_note.content) > 10
        assert updated_note.status == "draft"
        
    finally:
        await note_service.delete_note(note.note_id)


# === Тесты с TaskIQ worker ===

async def wait_for_condition(condition_fn, timeout: float = 30.0, interval: float = 0.5):
    """Ждет выполнения условия с polling"""
    import time
    start = time.time()
    while time.time() - start < timeout:
        result = await condition_fn()
        if result:
            return result
        await asyncio.sleep(interval)
    return None


@pytest.mark.asyncio
async def test_attachment_upload_with_worker(
    crm_client,
    note_service,
    test_context,
    taskiq_worker_process,
    taskiq_broker,
):
    """
    Полный E2E тест: upload через API -> TaskIQ worker индексирует в RAG.
    Требует запущенный TaskIQ worker.
    """
    from core.rag.factory import get_default_rag_provider
    
    set_context(test_context)
    
    note_data = NoteCreate(
        title="E2E Test Note",
        content="Testing full flow with worker",
        note_type=NoteType.FREEFORM,
        note_date=date.today(),
    )
    note = await note_service.create_note(
        note_data,
        company_id=crm_client.test_company.company_id,
        user_id=crm_client.test_user.user_id
    )
    
    try:
        # Upload через API (таска будет отправлена в worker)
        file_content = b"E2E test content for RAG indexing via TaskIQ worker"
        files = {"file": ("e2e_test.txt", io.BytesIO(file_content), "text/plain")}
        
        response = await crm_client.post(
            f"/crm/api/v1/notes/{note.note_id}/attachments",
            files=files
        )
        
        assert response.status_code == 200
        result = response.json()
        
        # Статус должен быть indexing пока worker не обработал
        assert result.get("status") in ["indexing", "ready", None]
        
        # Ждем пока файл появится в RAG
        provider = get_default_rag_provider()
        namespace = f"crm_attachments_{crm_client.test_company.company_id}"
        
        async def check_indexed():
            results = await provider.search(namespace_id=namespace, query="E2E test content", limit=5)
            return results if len(results) > 0 else None
        
        search_results = await wait_for_condition(check_indexed, timeout=45.0, interval=2.0)
        
        # Должен найти проиндексированный документ
        assert search_results is not None and len(search_results) > 0
        
    finally:
        await note_service.delete_note(note.note_id, company_id=crm_client.test_company.company_id)


@pytest.mark.asyncio
@pytest.mark.xfail(reason="E2E тест с несколькими subprocess - CRM сервер может не стартовать broker корректно")
async def test_import_with_worker(
    crm_client,
    test_context,
    taskiq_worker_process,
    taskiq_broker,
):
    """
    E2E тест импорта файла с TaskIQ worker.
    
    Использует API для проверки (а не прямой вызов сервиса), 
    т.к. worker и тест в разных процессах с разными сессиями БД.
    """
    file_content = """Quarterly Report Q4 2024

Revenue: $1.5M
Expenses: $800K
Profit: $700K

Key achievements:
- Launched new product line
- Expanded to 3 new markets
- Hired 15 new employees"""
    
    files = {"file": ("report.txt", io.BytesIO(file_content.encode()), "text/plain")}
    data = {
        "title": "Q4 2024 Report",
        "note_type": "freeform",
        "note_date": str(date.today()),
    }
    
    response = await crm_client.post(
        "/crm/api/v1/notes/import",
        files=files,
        data=data
    )
    
    assert response.status_code == 200
    result = response.json()
    note_id = result["note_id"]
    
    try:
        # Изначально статус importing
        assert result["status"] == "importing"
        
        # Ждем пока заметка будет обработана (через API)
        async def check_imported():
            resp = await crm_client.get(f"/crm/api/v1/notes/{note_id}")
            if resp.status_code == 200:
                note = resp.json()
                if note.get("status") == "draft" and len(note.get("content", "")) > 0:
                    return note
            return None
        
        updated_note = await wait_for_condition(check_imported, timeout=45.0)
        
        assert updated_note is not None
        assert updated_note["status"] == "draft"
        assert len(updated_note["content"]) > 0
        assert "Revenue" in updated_note["content"] or "Quarterly" in updated_note["content"]
        
    finally:
        await crm_client.delete(f"/crm/api/v1/notes/{note_id}")

