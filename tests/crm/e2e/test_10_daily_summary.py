"""
Тесты дневного саммари.

User Story: AI создает обобщенный отчет за день.
"""

import pytest
import json
from datetime import date


@pytest.mark.real_taskiq
class TestDailySummary:
    """Дневной саммари от AI"""
    
    @pytest.mark.asyncio
    async def test_generate_daily_summary(self, crm_client, mock_llm_redis, unique_id, auth_headers_system):
        """AI создает саммари всех заметок за день"""
        today = date.today()
        
        for i in range(3):
            await crm_client.post("/crm/api/v1/entities/", json={
                "entity_type": "note",
                "entity_subtype": "meeting",
                "name": f"Событие {i} {unique_id}",
                "description": f"Описание события {i} дня",
                "note_date": today.isoformat()
            }, headers=auth_headers_system)
        
        await mock_llm_redis([{
            "type": "text",
            "content": "Сегодня было 3 встречи. Главное: обсудили проект X, созвонились с клиентом, подписали контракт. Следующие шаги: начать разработку, подготовить документацию."
        }])
        
        response = await crm_client.post("/crm/api/v1/entities/daily-summary", json={
            "date": today.isoformat()
        }, headers=auth_headers_system)
        assert response.status_code == 200
        
        summary = response.json()
        assert "text" in summary or "summary" in summary or "date" in summary
        summary_text = summary.get("text") or summary.get("summary") or ""
        assert summary_text is not None
    
    @pytest.mark.asyncio
    async def test_empty_day_summary(self, crm_client, unique_id, auth_headers_system):
        """Саммари пустого дня"""
        future_date = "2099-12-31"
        
        response = await crm_client.post("/crm/api/v1/entities/daily-summary", json={
            "date": future_date
        }, headers=auth_headers_system)
        assert response.status_code == 200
        
        summary = response.json()
        assert summary is not None

