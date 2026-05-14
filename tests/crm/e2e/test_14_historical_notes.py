"""
Тесты заметок с прошедшей датой.

User Story: Создание заметок задним числом для переноса старых данных.
"""

from datetime import date, timedelta

import pytest


class TestHistoricalNotes:
    """Заметки с прошедшей датой"""

    @pytest.mark.asyncio
    async def test_create_note_past_date(self, crm_client, unique_id, auth_headers_system):
        """Создание заметки задним числом"""
        past_date = (date.today() - timedelta(days=30)).isoformat()

        response = await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "entity_subtype": "meeting",
            "name": f"Историческая заметка {unique_id}",
            "description": "Событие месяц назад",
            "note_date": past_date
        }, headers=auth_headers_system)
        assert response.status_code == 200

        note = response.json()
        assert note["note_date"] == past_date

    @pytest.mark.asyncio
    async def test_timeline_order(self, crm_client, unique_id, auth_headers_system):
        """Заметки отображаются в хронологическом порядке"""
        test_user_id = f"test_user_{unique_id}"
        dates = [
            (date.today() - timedelta(days=2)).isoformat(),
            (date.today() - timedelta(days=1)).isoformat(),
            date.today().isoformat()
        ]

        for i, note_date in enumerate(dates):
            await crm_client.post("/crm/api/v1/entities/", json={
                "entity_type": "note",
                "name": f"Note day {i} {unique_id}",
                "note_date": note_date,
                "user_id": test_user_id
            }, headers=auth_headers_system)

        list_resp = await crm_client.post(
            "/crm/api/v1/entities/query",
            json={
                "entity_type": "note",
                "limit": 100,
                "filters": {"field": "user_id", "op": "$eq", "value": test_user_id},
            },
            headers=auth_headers_system,
        )
        assert list_resp.status_code == 200
        notes = list_resp.json()["items"]

        assert len(notes) >= 3
        for n in notes:
            assert n["user_id"] == test_user_id

    @pytest.mark.asyncio
    async def test_filter_by_date_range(self, crm_client, unique_id, auth_headers_system):
        """Фильтрация по диапазону исторических дат"""
        test_user_id = f"test_user_{unique_id}"
        start_date = (date.today() - timedelta(days=60)).isoformat()
        end_date = (date.today() - timedelta(days=30)).isoformat()

        await crm_client.post("/crm/api/v1/entities/", json={
            "entity_type": "note",
            "name": f"Old note {unique_id}",
            "note_date": (date.today() - timedelta(days=45)).isoformat(),
            "user_id": test_user_id
        }, headers=auth_headers_system)

        filter_resp = await crm_client.post(
            "/crm/api/v1/entities/query",
            json={
                "entity_type": "note",
                "limit": 100,
                "filters": {
                    "$and": [
                        {"field": "user_id", "op": "$eq", "value": test_user_id},
                        {"field": "note_date", "op": "$gte", "value": start_date},
                        {"field": "note_date", "op": "$lte", "value": end_date},
                    ]
                },
            },
            headers=auth_headers_system,
        )
        assert filter_resp.status_code == 200
        filtered = filter_resp.json()["items"]
        assert len(filtered) >= 1
        for n in filtered:
            assert n["user_id"] == test_user_id

