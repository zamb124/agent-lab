"""
Тесты дневного саммари.

User Story: AI создает обобщенный отчет за день.
"""

import pytest
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
        
        first_response = await crm_client.post("/crm/api/v1/entities/daily-summary", json={
            "date": today.isoformat()
        }, headers=auth_headers_system)
        assert first_response.status_code == 200
        first_payload = first_response.json()
        assert first_payload["date"] == today.isoformat()
        assert "revalidating" in first_payload
        assert "stale" in first_payload
        assert "source_version" in first_payload

        assert first_payload.get("source_version", {}).get("notes_count", 0) >= 3
    
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
        assert "revalidating" in summary
        assert "stale" in summary

    @pytest.mark.asyncio
    async def test_summary_becomes_stale_after_note_update(
        self,
        crm_client,
        mock_llm_redis,
        unique_id,
        auth_headers_system,
    ):
        today = date.today().isoformat()
        create_response = await crm_client.post(
            "/crm/api/v1/entities",
            json={
                "entity_type": "note",
                "entity_subtype": "meeting",
                "name": f"Обновляемая заметка {unique_id}",
                "description": "Версия 1",
                "note_date": today,
            },
            headers=auth_headers_system,
        )
        assert create_response.status_code == 200
        entity_id = create_response.json()["entity_id"]

        await mock_llm_redis([{"type": "text", "content": "Итог версии 1"}])

        update_response = await crm_client.put(
            f"/crm/api/v1/entities/{entity_id}",
            json={"description": "Версия 2"},
            headers=auth_headers_system,
        )
        assert update_response.status_code == 200

        stale_response = await crm_client.post(
            "/crm/api/v1/entities/daily-summary",
            json={"date": today},
            headers=auth_headers_system,
        )
        assert stale_response.status_code == 200
        stale_payload = stale_response.json()
        assert stale_payload["stale"] is True
        assert stale_payload["revalidating"] is True

        await mock_llm_redis([{"type": "text", "content": "Итог версии 2"}])

    @pytest.mark.asyncio
    async def test_note_date_change_marks_old_and_new_dates_dirty(
        self,
        crm_client,
        mock_llm_redis,
        unique_id,
        auth_headers_system,
    ):
        today = date.today().isoformat()
        another_day = "2099-01-02"
        create_response = await crm_client.post(
            "/crm/api/v1/entities",
            json={
                "entity_type": "note",
                "entity_subtype": "meeting",
                "name": f"Смена даты {unique_id}",
                "description": "Исходный день",
                "note_date": today,
            },
            headers=auth_headers_system,
        )
        assert create_response.status_code == 200
        entity_id = create_response.json()["entity_id"]

        await mock_llm_redis([{"type": "text", "content": "Итог нового дня"}])
        update_response = await crm_client.put(
            f"/crm/api/v1/entities/{entity_id}",
            json={"note_date": another_day},
            headers=auth_headers_system,
        )
        assert update_response.status_code == 200

        old_stale = await crm_client.post(
            "/crm/api/v1/entities/daily-summary",
            json={"date": today},
            headers=auth_headers_system,
        )
        assert old_stale.status_code == 200
        old_stale_payload = old_stale.json()
        assert old_stale_payload["stale"] is True
        assert old_stale_payload["revalidating"] is True

        new_stale = await crm_client.post(
            "/crm/api/v1/entities/daily-summary",
            json={"date": another_day},
            headers=auth_headers_system,
        )
        assert new_stale.status_code == 200
        new_stale_payload = new_stale.json()
        assert new_stale_payload["revalidating"] is True


    @pytest.mark.asyncio
    async def test_summary_rebuild_triggered_after_note_delete(
        self,
        crm_client,
        mock_llm_redis,
        unique_id,
        auth_headers_system,
    ):
        today = date.today().isoformat()
        create_response = await crm_client.post(
            "/crm/api/v1/entities",
            json={
                "entity_type": "note",
                "entity_subtype": "meeting",
                "name": f"Удаляемая заметка {unique_id}",
                "description": "Для удаления",
                "note_date": today,
            },
            headers=auth_headers_system,
        )
        assert create_response.status_code == 200
        entity_id = create_response.json()["entity_id"]

        await mock_llm_redis([{"type": "text", "content": "Итог до удаления"}])

        delete_response = await crm_client.delete(
            f"/crm/api/v1/entities/{entity_id}",
            headers=auth_headers_system,
        )
        assert delete_response.status_code == 200

        stale_response = await crm_client.post(
            "/crm/api/v1/entities/daily-summary",
            json={"date": today},
            headers=auth_headers_system,
        )
        assert stale_response.status_code == 200
        stale_payload = stale_response.json()
        assert stale_payload["stale"] is True
        assert stale_payload["revalidating"] is True

        await mock_llm_redis([{"type": "text", "content": "Итог после удаления"}])

