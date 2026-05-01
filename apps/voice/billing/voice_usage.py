"""Биллинг voice-сессий."""

from __future__ import annotations

import asyncio

from core.logging import get_logger

logger = get_logger(__name__)


class VoiceUsageTracker:
    """Отслеживает длительность голосовых сессий и фиксирует usage."""

    def __init__(
        self,
        *,
        resource_name: str = "voice:session_minute",
    ) -> None:
        self._resource_name = resource_name

    async def track_and_bill(
        self,
        duration_seconds: float,
        company_id: str,
        billing_service,
    ) -> None:
        """Зафиксировать usage в billing за поминутную голосовую сессию."""
        if duration_seconds <= 0:
            return

        quantity = max(1, int(duration_seconds / 60))
        await billing_service.record_usage(
            company_id=company_id,
            resource_name=self._resource_name,
            quantity=float(quantity),
        )
        logger.info(
            "voice usage зафиксирован: company_id=%s duration=%.0fs quantity=%d",
            company_id,
            duration_seconds,
            quantity,
        )
