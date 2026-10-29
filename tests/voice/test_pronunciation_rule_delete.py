"""Чтение и удаление PronunciationRule по области компании и rule_id."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from core.clients.tts_pronunciation.models import (
    PronunciationRule,
    PronunciationRulePatch,
    PronunciationRuleWrite,
)


async def _insert(
    company_id: str | None,
    pattern: str,
    *,
    enabled: bool = True,
    created_at: datetime | None = None,
) -> PronunciationRule:
    row = PronunciationRule(
        pronunciation_rule_id=str(uuid4()),
        company_id=company_id,
        kind="alias",
        pattern=pattern,
        replacement="spoken",
        enabled=enabled,
    )
    if created_at is not None:
        row.created_at = created_at
    return await PronunciationRule.objects.create(instance=row)


@pytest.mark.asyncio
async def test_delete_by_company_scope_and_rule_id(unique_id: str) -> None:
    company_id = f"pron-{unique_id}"
    other_company_id = f"pron-other-{unique_id}"
    company_rule = await _insert(company_id, f"a-{unique_id}")
    other_rule = await _insert(other_company_id, f"b-{unique_id}")
    platform_rule = await _insert(None, f"p-{unique_id}")

    assert (
        await PronunciationRule.delete_by_company_scope_and_rule_id(
            company_id=other_company_id,
            rule_id=company_rule.pronunciation_rule_id,
        )
        is False
    )
    assert (
        await PronunciationRule.by_company_scope_and_rule_id(
            company_id=company_id,
            rule_id=company_rule.pronunciation_rule_id,
        )
        is not None
    )
    assert (
        await PronunciationRule.delete_by_company_scope_and_rule_id(
            company_id=company_id,
            rule_id=platform_rule.pronunciation_rule_id,
        )
        is False
    )

    assert (
        await PronunciationRule.delete_by_company_scope_and_rule_id(
            company_id=company_id,
            rule_id=company_rule.pronunciation_rule_id,
        )
        is True
    )
    assert (
        await PronunciationRule.delete_by_company_scope_and_rule_id(
            company_id=company_id,
            rule_id=company_rule.pronunciation_rule_id,
        )
        is False
    )
    assert (
        await PronunciationRule.delete_by_company_scope_and_rule_id(
            company_id=None,
            rule_id=platform_rule.pronunciation_rule_id,
        )
        is True
    )
    with pytest.raises(ValueError, match="company_id cannot be empty"):
        _ = await PronunciationRule.delete_by_company_scope_and_rule_id(
            company_id="",
            rule_id=other_rule.pronunciation_rule_id,
        )
    with pytest.raises(ValueError, match="rule_id cannot be empty"):
        _ = await PronunciationRule.delete_by_company_scope_and_rule_id(
            company_id=other_company_id,
            rule_id="",
        )
    assert (
        await PronunciationRule.delete_by_company_scope_and_rule_id(
            company_id=other_company_id,
            rule_id=other_rule.pronunciation_rule_id,
        )
        is True
    )


@pytest.mark.asyncio
async def test_by_company_scope_and_rule_id(unique_id: str) -> None:
    company_id = f"pron-read-{unique_id}"
    other_company_id = f"pron-read-other-{unique_id}"
    company_rule = await _insert(company_id, f"read-a-{unique_id}")
    platform_rule = await _insert(None, f"read-p-{unique_id}")

    found = await PronunciationRule.by_company_scope_and_rule_id(
        company_id=company_id,
        rule_id=company_rule.pronunciation_rule_id,
    )
    assert found is not None
    assert found.pronunciation_rule_id == company_rule.pronunciation_rule_id
    assert (
        await PronunciationRule.by_company_scope_and_rule_id(
            company_id=other_company_id,
            rule_id=company_rule.pronunciation_rule_id,
        )
        is None
    )
    assert (
        await PronunciationRule.by_company_scope_and_rule_id(
            company_id=company_id,
            rule_id=platform_rule.pronunciation_rule_id,
        )
        is None
    )
    platform_found = await PronunciationRule.by_company_scope_and_rule_id(
        company_id=None,
        rule_id=platform_rule.pronunciation_rule_id,
    )
    assert platform_found is not None
    assert (
        await PronunciationRule.by_company_scope_and_rule_id(
            company_id=company_id,
            rule_id=str(uuid4()),
        )
        is None
    )
    with pytest.raises(ValueError, match="company_id cannot be empty"):
        _ = await PronunciationRule.by_company_scope_and_rule_id(
            company_id="",
            rule_id=company_rule.pronunciation_rule_id,
        )
    with pytest.raises(ValueError, match="rule_id cannot be empty"):
        _ = await PronunciationRule.by_company_scope_and_rule_id(
            company_id=company_id,
            rule_id="",
        )
    assert (
        await PronunciationRule.delete_by_company_scope_and_rule_id(
            company_id=company_id,
            rule_id=company_rule.pronunciation_rule_id,
        )
        is True
    )
    assert (
        await PronunciationRule.delete_by_company_scope_and_rule_id(
            company_id=None,
            rule_id=platform_rule.pronunciation_rule_id,
        )
        is True
    )


@pytest.mark.asyncio
async def test_list_for_company_scope_orders_and_hides_other_scope(unique_id: str) -> None:
    company_id = f"pron-list-{unique_id}"
    other_company_id = f"pron-list-other-{unique_id}"
    older = datetime(2020, 1, 1, tzinfo=UTC)
    newer = older + timedelta(seconds=1)
    first = await _insert(company_id, f"first-{unique_id}", created_at=older)
    second = await _insert(
        company_id,
        f"second-{unique_id}",
        enabled=False,
        created_at=newer,
    )
    other = await _insert(other_company_id, f"other-{unique_id}")
    platform = await _insert(None, f"platform-{unique_id}")

    company_rows = await PronunciationRule.list_for_company_scope_by_created_at_asc(company_id=company_id)
    assert [row.pronunciation_rule_id for row in company_rows] == [
        first.pronunciation_rule_id,
        second.pronunciation_rule_id,
    ]
    enabled_rows = await PronunciationRule.list_enabled_for_company_scope_by_created_at_asc(company_id=company_id)
    assert [row.pronunciation_rule_id for row in enabled_rows] == [first.pronunciation_rule_id]
    platform_ids = {
        row.pronunciation_rule_id
        for row in await PronunciationRule.list_for_company_scope_by_created_at_asc(company_id=None)
    }
    assert platform.pronunciation_rule_id in platform_ids
    assert first.pronunciation_rule_id not in platform_ids
    with pytest.raises(ValueError, match="company_id cannot be empty"):
        _ = await PronunciationRule.list_for_company_scope_by_created_at_asc(company_id="")
    for scope, rule in (
        (company_id, first),
        (company_id, second),
        (other_company_id, other),
        (None, platform),
    ):
        assert (
            await PronunciationRule.delete_by_company_scope_and_rule_id(
                company_id=scope,
                rule_id=rule.pronunciation_rule_id,
            )
            is True
        )


@pytest.mark.asyncio
async def test_update_by_company_scope_and_rule_id_patches_only_set_fields(unique_id: str) -> None:
    company_id = f"pron-upd-{unique_id}"
    other_company_id = f"pron-upd-other-{unique_id}"
    row = await _insert(company_id, f"keep-{unique_id}")
    missed = await PronunciationRule.update_by_company_scope_and_rule_id(
        company_id=other_company_id,
        rule_id=row.pronunciation_rule_id,
        patch=PronunciationRulePatch(pattern=f"stolen-{unique_id}"),
    )
    assert missed is None
    unchanged = await PronunciationRule.by_company_scope_and_rule_id(
        company_id=company_id,
        rule_id=row.pronunciation_rule_id,
    )
    assert unchanged is not None
    assert unchanged.pattern == f"keep-{unique_id}"
    assert unchanged.replacement == "spoken"

    updated = await PronunciationRule.update_by_company_scope_and_rule_id(
        company_id=company_id,
        rule_id=row.pronunciation_rule_id,
        patch=PronunciationRulePatch(replacement=f"said-{unique_id}"),
    )
    assert updated is not None
    assert updated.pattern == f"keep-{unique_id}"
    assert updated.replacement == f"said-{unique_id}"
    assert (
        await PronunciationRule.update_by_company_scope_and_rule_id(
            company_id=company_id,
            rule_id=str(uuid4()),
            patch=PronunciationRulePatch(note="missing"),
        )
        is None
    )
    with pytest.raises(ValueError, match="company_id cannot be empty"):
        _ = await PronunciationRule.update_by_company_scope_and_rule_id(
            company_id="",
            rule_id=row.pronunciation_rule_id,
            patch=PronunciationRulePatch(note="x"),
        )
    still = await PronunciationRule.by_company_scope_and_rule_id(
        company_id=company_id,
        rule_id=row.pronunciation_rule_id,
    )
    assert still is not None
    assert still.pattern == f"keep-{unique_id}"
    assert (
        await PronunciationRule.delete_by_company_scope_and_rule_id(
            company_id=company_id,
            rule_id=row.pronunciation_rule_id,
        )
        is True
    )


def _write(pattern: str) -> PronunciationRuleWrite:
    return PronunciationRuleWrite(kind="alias", pattern=pattern, replacement="spoken")


@pytest.mark.asyncio
async def test_create_for_company_scope_inserts_and_enforces_limit(unique_id: str) -> None:
    company_id = f"pron-new-{unique_id}"
    other_company_id = f"pron-new-other-{unique_id}"
    created = await PronunciationRule.create_for_company_scope(
        company_id=company_id,
        rule=_write(f"one-{unique_id}"),
        max_rules=1,
    )
    assert created.pronunciation_rule_id != ""
    found = await PronunciationRule.by_company_scope_and_rule_id(
        company_id=company_id,
        rule_id=created.pronunciation_rule_id,
    )
    assert found is not None
    assert found.pattern == f"one-{unique_id}"
    with pytest.raises(ValueError, match="Pronunciation rule limit reached"):
        _ = await PronunciationRule.create_for_company_scope(
            company_id=company_id,
            rule=_write(f"two-{unique_id}"),
            max_rules=1,
        )
    other = await PronunciationRule.create_for_company_scope(
        company_id=other_company_id,
        rule=_write(f"other-{unique_id}"),
        max_rules=1,
    )
    platform = await PronunciationRule.create_for_company_scope(
        company_id=None,
        rule=_write(f"platform-{unique_id}"),
    )
    assert (
        await PronunciationRule.by_company_scope_and_rule_id(
            company_id=company_id,
            rule_id=platform.pronunciation_rule_id,
        )
        is None
    )
    with pytest.raises(ValueError, match="max_rules is required"):
        _ = await PronunciationRule.create_for_company_scope(
            company_id=company_id,
            rule=_write(f"nolimit-{unique_id}"),
        )
    with pytest.raises(ValueError, match="company_id cannot be empty"):
        _ = await PronunciationRule.create_for_company_scope(
            company_id="",
            rule=_write(f"empty-{unique_id}"),
            max_rules=1,
        )
    for scope, rule_id in (
        (company_id, created.pronunciation_rule_id),
        (other_company_id, other.pronunciation_rule_id),
        (None, platform.pronunciation_rule_id),
    ):
        assert (
            await PronunciationRule.delete_by_company_scope_and_rule_id(
                company_id=scope,
                rule_id=rule_id,
            )
            is True
        )
