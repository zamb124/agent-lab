"""AmoCRM: дата заметки (note_date) для ежедневника и upsert без пропусков."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from apps.crm.db.models import CRMEntity
from apps.crm.integrations.amocrm.mapping import AMO_PROVIDER_ID
from apps.crm.integrations.amocrm.service import AmoCRMIntegrationService
from apps.crm.integrations.entity_upsert import upsert_canonical_by_external_ref
from apps.crm.integrations.external_ref import external_ref_now, merge_external_refs
from core.context import clear_context, set_context
from core.models.context_models import Context
from core.models.identity_models import Company, User

pytestmark = pytest.mark.timeout(30, func_only=True)


def test_note_date_from_amo_unix_int() -> None:
    got = AmoCRMIntegrationService._note_date_from_amo_created_at(1_704_067_200)
    assert got == date(2024, 1, 1)


def test_note_date_from_amo_unix_string() -> None:
    got = AmoCRMIntegrationService._note_date_from_amo_created_at("1704067200")
    assert got == date(2024, 1, 1)


def test_note_date_from_amo_iso_z() -> None:
    got = AmoCRMIntegrationService._note_date_from_amo_created_at(
        "2024-06-15T12:00:00Z",
    )
    assert got == date(2024, 6, 15)


def test_note_date_invalid_input_raises() -> None:
    for value in ("not-a-date", None, []):
        with pytest.raises(ValueError):
            AmoCRMIntegrationService._note_date_from_amo_created_at(value)


@pytest.mark.asyncio
async def test_upsert_note_without_note_date_sets_today(
    crm_container,
    unique_id: str,
    system_user_id: str,
) -> None:
    ns = f"amo_nd_{unique_id}"
    ctx = Context(
        user=User(user_id=system_user_id, name="Test"),
        active_company=Company(company_id="system", name="System"),
        channel="test",
        active_namespace=ns,
    )
    set_context(ctx)
    try:
        ent, created = await upsert_canonical_by_external_ref(
            entity_repo=crm_container.entity_repository,
            namespace=ns,
            company_id="system",
            user_id=system_user_id,
            entity_type="note",
            source_id=AMO_PROVIDER_ID,
            record_id=f"nd-{unique_id}",
            name="Note without explicit note_date",
            patch_attributes={},
            account_key="sub_amocrm",
            note_date=None,
        )
        assert created is True
        assert ent.note_date is not None
        assert ent.note_date == datetime.now(timezone.utc).date()
    finally:
        clear_context()


@pytest.mark.asyncio
async def test_upsert_note_update_backfills_null_note_date(
    crm_container,
    unique_id: str,
    system_user_id: str,
) -> None:
    ns = f"amo_nd2_{unique_id}"
    rid = f"nd2-{unique_id}"
    ctx = Context(
        user=User(user_id=system_user_id, name="Test"),
        active_company=Company(company_id="system", name="System"),
        channel="test",
        active_namespace=ns,
    )
    set_context(ctx)
    try:
        ref = external_ref_now(record_id=rid, account_key="sub_amocrm")
        attrs = merge_external_refs({}, source_id=AMO_PROVIDER_ID, ref=ref)
        ent0 = CRMEntity(
            entity_id=f"manual_{unique_id}",
            company_id="system",
            namespace=ns,
            entity_type="note",
            name="Legacy null note_date",
            description="x",
            attributes=attrs,
            tags=[],
            user_id=system_user_id,
            note_date=None,
        )
        await crm_container.entity_repository.create(ent0)

        ent1, created1 = await upsert_canonical_by_external_ref(
            entity_repo=crm_container.entity_repository,
            namespace=ns,
            company_id="system",
            user_id=system_user_id,
            entity_type="note",
            source_id=AMO_PROVIDER_ID,
            record_id=rid,
            name="Patched name",
            patch_attributes={},
            account_key="sub_amocrm",
            note_date=None,
        )
        assert created1 is False
        assert ent1.entity_id == ent0.entity_id
        assert ent1.note_date is not None
        assert ent1.note_date == datetime.now(timezone.utc).date()
    finally:
        clear_context()
