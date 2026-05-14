"""
Тесты дневного саммари.

User Story: AI создает обобщенный отчет за день.
"""

from datetime import date

import pytest

from tests.fixtures.crm_test_setup import (
    wait_daily_summary_rebuild_done,
)


@pytest.mark.real_taskiq
class TestDailySummary:
    """Дневной саммари от AI"""

    @pytest.mark.asyncio
    async def test_generate_daily_summary(self, crm_client, unique_id, auth_headers_system):
        """Саммари за день: версия источника и фоновый пересчёт без LLM, пока нет ai_analysis_applied_at."""
        today = f"2096-05-{hash(unique_id) % 28 + 1:02d}"

        for i in range(3):
            await crm_client.post("/crm/api/v1/entities/", json={
                "entity_type": "note",
                "entity_subtype": "meeting",
                "name": f"Событие {i} {unique_id}",
                "description": f"Описание события {i} дня",
                "note_date": today
            }, headers=auth_headers_system)

        first_response = await crm_client.post("/crm/api/v1/entities/daily-summary", json={
            "date": today
        }, headers=auth_headers_system)
        assert first_response.status_code == 200
        first_payload = first_response.json()
        assert first_payload["date"] == today
        assert "revalidating" in first_payload
        assert "stale" in first_payload
        assert "source_version" in first_payload

        assert first_payload.get("source_version", {}).get("notes_count", 0) >= 3

        await wait_daily_summary_rebuild_done(
            crm_client,
            auth_headers_system,
            date_str=today,
        )

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

        await wait_daily_summary_rebuild_done(
            crm_client,
            auth_headers_system,
            date_str=today,
        )

    @pytest.mark.asyncio
    async def test_note_date_change_marks_old_and_new_dates_dirty(
        self,
        crm_client,
        unique_id,
        auth_headers_system,
    ):
        original_day = f"2098-06-{hash(unique_id) % 28 + 1:02d}"
        another_day = "2098-07-15"
        create_response = await crm_client.post(
            "/crm/api/v1/entities",
            json={
                "entity_type": "note",
                "entity_subtype": "meeting",
                "name": f"Смена даты {unique_id}",
                "description": "Исходный день",
                "note_date": original_day,
            },
            headers=auth_headers_system,
        )
        assert create_response.status_code == 200
        entity_id = create_response.json()["entity_id"]

        first_summary = await crm_client.post(
            "/crm/api/v1/entities/daily-summary",
            json={"date": original_day},
            headers=auth_headers_system,
        )
        assert first_summary.status_code == 200
        await wait_daily_summary_rebuild_done(
            crm_client,
            auth_headers_system,
            date_str=original_day,
        )

        update_response = await crm_client.put(
            f"/crm/api/v1/entities/{entity_id}",
            json={"note_date": another_day},
            headers=auth_headers_system,
        )
        assert update_response.status_code == 200

        old_stale = await crm_client.post(
            "/crm/api/v1/entities/daily-summary",
            json={"date": original_day},
            headers=auth_headers_system,
        )
        assert old_stale.status_code == 200
        old_stale_payload = old_stale.json()
        assert old_stale_payload.get("source_version", {}).get("notes_count") == 0
        assert old_stale_payload["stale"] is False
        assert "не найдено" in (old_stale_payload.get("summary") or "")

        await wait_daily_summary_rebuild_done(
            crm_client,
            auth_headers_system,
            date_str=another_day,
        )
        new_final = await crm_client.post(
            "/crm/api/v1/entities/daily-summary",
            json={"date": another_day},
            headers=auth_headers_system,
        )
        assert new_final.status_code == 200
        new_payload = new_final.json()
        assert new_payload["source_version"].get("notes_count", 0) >= 1

    @pytest.mark.asyncio
    async def test_summary_rebuild_triggered_after_note_delete(
        self,
        crm_client,
        unique_id,
        auth_headers_system,
    ):
        isolated_date = f"2097-09-{hash(unique_id) % 28 + 1:02d}"
        create_response = await crm_client.post(
            "/crm/api/v1/entities",
            json={
                "entity_type": "note",
                "entity_subtype": "meeting",
                "name": f"Удаляемая заметка {unique_id}",
                "description": "Для удаления",
                "note_date": isolated_date,
            },
            headers=auth_headers_system,
        )
        assert create_response.status_code == 200
        entity_id = create_response.json()["entity_id"]

        pre_summary = await crm_client.post(
            "/crm/api/v1/entities/daily-summary",
            json={"date": isolated_date},
            headers=auth_headers_system,
        )
        assert pre_summary.status_code == 200
        await wait_daily_summary_rebuild_done(
            crm_client,
            auth_headers_system,
            date_str=isolated_date,
        )

        delete_response = await crm_client.delete(
            f"/crm/api/v1/entities/{entity_id}",
            headers=auth_headers_system,
        )
        assert delete_response.status_code == 200

        stale_response = await crm_client.post(
            "/crm/api/v1/entities/daily-summary",
            json={"date": isolated_date},
            headers=auth_headers_system,
        )
        assert stale_response.status_code == 200
        stale_payload = stale_response.json()
        assert stale_payload.get("source_version", {}).get("notes_count") == 0
        assert stale_payload["stale"] is False
        assert "не найдено" in (stale_payload.get("summary") or "")

