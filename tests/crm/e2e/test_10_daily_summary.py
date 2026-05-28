"""
Тесты дневного саммари.

User Story: AI создает обобщенный отчет за день.
"""

from datetime import date
from typing import cast

import pytest
from httpx import AsyncClient, Response

from tests.crm.e2e._json_helpers import json_object, object_dict, object_str
from tests.fixtures.crm_test_setup import wait_daily_summary_rebuild_done


def _http_json(response: Response) -> dict[str, object]:
    return json_object(cast(object, response.json()))


def _entity_id(response: Response) -> str:
    return object_str(_http_json(response).get("entity_id"), field="entity_id")


def _json_bool(payload: dict[str, object], key: str) -> bool:
    value = payload[key]
    if not isinstance(value, bool):
        raise AssertionError(f"{key} must be bool")
    return value


def _source_version(payload: dict[str, object]) -> dict[str, object]:
    return object_dict(payload.get("source_version"), field="source_version")


def _notes_count(payload: dict[str, object]) -> int:
    notes_count = _source_version(payload).get("notes_count")
    if not isinstance(notes_count, int):
        raise AssertionError("notes_count must be int")
    return notes_count


def _optional_summary_text(payload: dict[str, object]) -> str:
    summary_value = payload.get("summary")
    if summary_value is None:
        return ""
    return object_str(summary_value, field="summary")


@pytest.mark.real_taskiq
class TestDailySummary:
    """Дневной саммари от AI"""

    @pytest.mark.asyncio
    async def test_generate_daily_summary(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Саммари за день: версия источника и фоновый пересчёт без LLM, пока нет ai_analysis_applied_at."""
        today = f"2096-05-{hash(unique_id) % 28 + 1:02d}"

        for i in range(3):
            _ = await crm_client.post("/crm/api/v1/entities/", json={
                "entity_type": "note",
                "entity_subtype": "meeting",
                "name": f"Событие {i} {unique_id}",
                "description": f"Описание события {i} дня",
                "note_date": today,
            }, headers=auth_headers_system)

        first_response = await crm_client.post("/crm/api/v1/entities/daily-summary", json={
            "date": today,
        }, headers=auth_headers_system)
        assert first_response.status_code == 200
        first_payload = _http_json(first_response)
        assert object_str(first_payload.get("date"), field="date") == today
        assert "revalidating" in first_payload
        assert "stale" in first_payload
        assert "source_version" in first_payload

        assert _notes_count(first_payload) >= 3

        _ = await wait_daily_summary_rebuild_done(
            crm_client,
            auth_headers_system,
            date_str=today,
        )

    @pytest.mark.asyncio
    async def test_empty_day_summary(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
        """Саммари пустого дня"""
        _ = unique_id
        future_date = "2099-12-31"

        response = await crm_client.post("/crm/api/v1/entities/daily-summary", json={
            "date": future_date,
        }, headers=auth_headers_system)
        assert response.status_code == 200

        summary = _http_json(response)
        assert summary is not None
        assert "revalidating" in summary
        assert "stale" in summary

    @pytest.mark.asyncio
    async def test_summary_becomes_stale_after_note_update(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
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
        entity_id = _entity_id(create_response)

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
        stale_payload = _http_json(stale_response)
        assert _json_bool(stale_payload, "stale") is True
        assert _json_bool(stale_payload, "revalidating") is True

        _ = await wait_daily_summary_rebuild_done(
            crm_client,
            auth_headers_system,
            date_str=today,
        )

    @pytest.mark.asyncio
    async def test_note_date_change_marks_old_and_new_dates_dirty(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
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
        entity_id = _entity_id(create_response)

        first_summary = await crm_client.post(
            "/crm/api/v1/entities/daily-summary",
            json={"date": original_day},
            headers=auth_headers_system,
        )
        assert first_summary.status_code == 200
        _ = await wait_daily_summary_rebuild_done(
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
        old_stale_payload = _http_json(old_stale)
        assert _notes_count(old_stale_payload) == 0
        assert _json_bool(old_stale_payload, "stale") is False
        assert "не найдено" in _optional_summary_text(old_stale_payload)

        _ = await wait_daily_summary_rebuild_done(
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
        new_payload = _http_json(new_final)
        assert _notes_count(new_payload) >= 1

    @pytest.mark.asyncio
    async def test_summary_rebuild_triggered_after_note_delete(
        self,
        crm_client: AsyncClient,
        unique_id: str,
        auth_headers_system: dict[str, str],
    ) -> None:
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
        entity_id = _entity_id(create_response)

        pre_summary = await crm_client.post(
            "/crm/api/v1/entities/daily-summary",
            json={"date": isolated_date},
            headers=auth_headers_system,
        )
        assert pre_summary.status_code == 200
        _ = await wait_daily_summary_rebuild_done(
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
        stale_payload = _http_json(stale_response)
        assert _notes_count(stale_payload) == 0
        assert _json_bool(stale_payload, "stale") is False
        assert "не найдено" in _optional_summary_text(stale_payload)
