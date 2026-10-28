"""Журнал событий документа."""

from __future__ import annotations

import json

import pytest

from apps.office.models.event import OfficeDocumentEvent
from core.context import reset_context, set_context
from core.models.context_models import Context
from core.models.identity_models import Company, User, UserStatus


@pytest.mark.asyncio
async def test_append_writes_event_json(
    office_di,
    unique_id: str,
) -> None:
    _ = office_di
    company_id = f"co-{unique_id}"[:32]
    file_id = f"file-{unique_id}"
    user = User(
        user_id=f"user-{unique_id}",
        name="Office",
        status=UserStatus.ACTIVE,
        companies={company_id: ["owner"]},
        active_company_id=company_id,
    )
    company = Company(
        company_id=company_id,
        name=company_id,
        subdomain=company_id,
        owner_user_id=user.user_id,
    )
    token = set_context(
        Context(
            user=user,
            active_company=company,
            user_companies=[company],
            channel="test",
        )
    )
    try:
        await OfficeDocumentEvent.append_new_event(
            file_id=file_id,
            company_id=company_id,
            event_type="saved",
            user_id=user.user_id,
            payload={"kind": "saved"},
        )
        rows = await OfficeDocumentEvent.list_by_created_at_desc_for_file(file_id, limit=10)
        assert len(rows) == 1
        assert rows[0].event_type == "saved"
        assert rows[0].payload_json == json.dumps({"kind": "saved"}, ensure_ascii=False)
    finally:
        reset_context(token)
