"""Тесты VoiceUsageTracker."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.voice.billing.voice_usage import VoiceUsageTracker


async def test_voice_usage_zero_duration_does_not_bill(unique_id: str) -> None:
    tracker = VoiceUsageTracker()
    billing_service = MagicMock()
    billing_service.record_usage = AsyncMock()

    await tracker.track_and_bill(
        duration_seconds=0,
        company_id=f"company-{unique_id}",
        billing_service=billing_service,
    )

    billing_service.record_usage.assert_not_called()


async def test_voice_usage_negative_duration_does_not_bill(unique_id: str) -> None:
    tracker = VoiceUsageTracker()
    billing_service = MagicMock()
    billing_service.record_usage = AsyncMock()

    await tracker.track_and_bill(
        duration_seconds=-10,
        company_id=f"company-{unique_id}",
        billing_service=billing_service,
    )

    billing_service.record_usage.assert_not_called()


async def test_voice_usage_short_session_bills_one_minute(unique_id: str) -> None:
    tracker = VoiceUsageTracker()
    billing_service = MagicMock()
    billing_service.record_usage = AsyncMock()

    await tracker.track_and_bill(
        duration_seconds=30,
        company_id=f"company-{unique_id}",
        billing_service=billing_service,
    )

    billing_service.record_usage.assert_called_once_with(
        company_id=f"company-{unique_id}",
        resource_name="voice:session_minute",
        quantity=1.0,
    )


async def test_voice_usage_two_minutes_bills_two(unique_id: str) -> None:
    tracker = VoiceUsageTracker()
    billing_service = MagicMock()
    billing_service.record_usage = AsyncMock()

    await tracker.track_and_bill(
        duration_seconds=125,
        company_id=f"company-{unique_id}",
        billing_service=billing_service,
    )

    billing_service.record_usage.assert_called_once_with(
        company_id=f"company-{unique_id}",
        resource_name="voice:session_minute",
        quantity=2.0,
    )


async def test_voice_usage_custom_resource_name(unique_id: str) -> None:
    tracker = VoiceUsageTracker(resource_name="voice:custom_resource")
    billing_service = MagicMock()
    billing_service.record_usage = AsyncMock()

    await tracker.track_and_bill(
        duration_seconds=60,
        company_id=f"company-{unique_id}",
        billing_service=billing_service,
    )

    call_kwargs = billing_service.record_usage.call_args.kwargs
    assert call_kwargs["resource_name"] == "voice:custom_resource"
