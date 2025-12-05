"""
Тесты для API экспорта.
"""

import pytest
from datetime import date
from httpx import AsyncClient


class TestExportAPI:
    """Тесты API для экспорта данных"""
    
    @pytest.mark.asyncio
    async def test_export_note_html(self, crm_client: AsyncClient, test_note):
        """Тест экспорта заметки в HTML"""
        response = await crm_client.get(
            f"/crm/api/v1/export/note/{test_note.note_id}",
            params={"format": "html"}
        )
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        
        content = response.content.decode('utf-8')
        assert test_note.title in content
        assert "<!DOCTYPE html>" in content
    
    @pytest.mark.asyncio
    async def test_export_note_pdf(self, crm_client: AsyncClient, test_note):
        """Тест экспорта заметки в PDF (или HTML fallback)"""
        response = await crm_client.get(
            f"/crm/api/v1/export/note/{test_note.note_id}",
            params={"format": "pdf"}
        )
        
        assert response.status_code == 200
        # Может быть PDF или HTML в зависимости от наличия weasyprint
        content_type = response.headers["content-type"]
        assert "application/pdf" in content_type or "text/html" in content_type
    
    @pytest.mark.asyncio
    async def test_export_note_default_format(self, crm_client: AsyncClient, test_note):
        """Тест экспорта заметки без указания формата (по умолчанию PDF)"""
        response = await crm_client.get(
            f"/crm/api/v1/export/note/{test_note.note_id}"
        )
        
        assert response.status_code == 200
        # По умолчанию PDF
        assert "content-disposition" in response.headers
    
    @pytest.mark.asyncio
    async def test_export_note_not_found(self, crm_client: AsyncClient):
        """Тест экспорта несуществующей заметки"""
        response = await crm_client.get(
            "/crm/api/v1/export/note/nonexistent_note_id"
        )
        
        assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_export_note_with_summary(self, crm_client: AsyncClient, crm_container, test_company_id, test_user_id):
        """Тест экспорта заметки с AI резюме"""
        from apps.crm.db.models import Note
        from datetime import date
        import uuid
        
        note = Note(
            note_id=str(uuid.uuid4()),
            company_id=test_company_id,
            user_id=test_user_id,
            title="Заметка с резюме",
            content="Содержимое заметки для экспорта",
            note_type="meeting_minutes",
            note_date=date.today(),
            ai_summary="Это AI-сгенерированное резюме заметки"
        )
        await crm_container.note_repository.create(note)
        
        response = await crm_client.get(
            f"/crm/api/v1/export/note/{note.note_id}",
            params={"format": "html"}
        )
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert "AI-сгенерированное резюме" in content
    
    @pytest.mark.asyncio
    async def test_export_daily_report_html(self, crm_client: AsyncClient):
        """Тест экспорта дневного отчета в HTML"""
        today = date.today().isoformat()
        
        response = await crm_client.get(
            f"/crm/api/v1/export/daily-report/{today}",
            params={"format": "html"}
        )
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        
        content = response.content.decode('utf-8')
        assert "Отчет за" in content
    
    @pytest.mark.asyncio
    async def test_export_daily_report_pdf(self, crm_client: AsyncClient):
        """Тест экспорта дневного отчета в PDF"""
        today = date.today().isoformat()
        
        response = await crm_client.get(
            f"/crm/api/v1/export/daily-report/{today}",
            params={"format": "pdf"}
        )
        
        assert response.status_code == 200
        assert "content-disposition" in response.headers
    
    @pytest.mark.asyncio
    async def test_export_daily_report_with_notes(
        self, crm_client: AsyncClient, crm_container, test_company_id, test_user_id
    ):
        """Тест экспорта дневного отчета с заметками"""
        from apps.crm.db.models import Note
        import uuid
        
        today = date.today()
        
        # Создаем несколько заметок на сегодня
        for i in range(3):
            note = Note(
                note_id=str(uuid.uuid4()),
                company_id=test_company_id,
                user_id=test_user_id,
                title=f"Заметка дня #{i+1}",
                content=f"Содержимое заметки #{i+1}",
                note_type="freeform",
                note_date=today
            )
            await crm_container.note_repository.create(note)
        
        response = await crm_client.get(
            f"/crm/api/v1/export/daily-report/{today.isoformat()}",
            params={"format": "html"}
        )
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        
        # Проверяем что заметки присутствуют в отчете
        assert "Заметки" in content
    
    @pytest.mark.asyncio
    async def test_export_content_disposition_header(self, crm_client: AsyncClient, test_note):
        """Тест наличия заголовка Content-Disposition для скачивания"""
        response = await crm_client.get(
            f"/crm/api/v1/export/note/{test_note.note_id}",
            params={"format": "html"}
        )
        
        assert response.status_code == 200
        assert "content-disposition" in response.headers
        assert "attachment" in response.headers["content-disposition"]
        assert f"note_{test_note.note_id}" in response.headers["content-disposition"]

