"""
Helpers для записи биллинга STT/TTS-вызовов voice gateway и voice capabilities.

Прайсы живут в `conf.json` → `platform.billing.resource_base_prices`,
категории `stt`, `tts`, `vad` (см. конфиг). resource_name строится как
`<category>:<provider>` (например `stt:cloud_ru`, `tts:litserve`), чтобы
один и тот же ресурс на разных провайдерах считался отдельно. Если
конкретного провайдера в прайсе нет — действует ключ `*` категории
(каноничный fallback BillingService по правилу resource lookup).

Функции вызываются из:
- `apps/voice/api/transcribe.py` после батч-STT (секунды из ffprobe;
  при ошибке probe — без `record_stt_usage`, см. лог);
- `apps/voice/api/synthesize.py` после streaming-TTS-сессии;
- `apps/capability_gateway/services/registry.py` (`voice.transcribe_audio`,
  `voice.synthesize_speech`) — единый capability-контур для isolated runners.

Real-time длительность voice-сессии и поминутный учёт — в spans
``platform_tracing`` (`category=voice`, `resource_name="session_minute"`),
не через ``record_*_usage``.

Никаких неявных дефолтов: provider, company, user обязательны.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.billing import get_billing_service
from core.billing.service import COST_ORIGIN_COMPANY, COST_ORIGIN_PLATFORM
from core.logging import get_logger
from core.models.billing_models import UsageType
from core.models.identity_models import Company, User

logger = get_logger(__name__)


def _resolve_actor(*, user: User | None, company: Company | None) -> tuple[User, Company]:
    if user is None:
        raise ValueError("voice_usage: user обязателен.")
    if company is None:
        raise ValueError("voice_usage: company обязательна.")
    return user, company


async def record_stt_usage(
    *,
    user: User,
    company: Company,
    provider: str,
    audio_seconds: float,
    metadata: Mapping[str, Any] | None = None,
    cost_origin: str = COST_ORIGIN_PLATFORM,
) -> str:
    """Записать списание за STT-вызов.

    quantity = округлённое вверх число секунд аудио (минимум 1). При ``cost_origin=company``
    запись пишется с ``cost=0`` (компания платит провайдеру напрямую).
    """
    if not provider or not isinstance(provider, str):
        raise ValueError("voice_usage.record_stt_usage: provider обязателен.")
    if audio_seconds < 0:
        raise ValueError("voice_usage.record_stt_usage: audio_seconds < 0.")

    user_obj, company_obj = _resolve_actor(user=user, company=company)
    quantity = max(1, int(audio_seconds + 0.999))
    is_company = cost_origin == COST_ORIGIN_COMPANY
    resource_name = "stt:byok" if is_company else f"stt:{provider}"

    billing = get_billing_service()
    if is_company:
        total_cost = 0.0
    else:
        unit_cost = await billing.get_resource_cost_for_company(company_obj, resource_name)
        total_cost = unit_cost * quantity

    return await billing.record_usage(
        user=user_obj,
        company=company_obj,
        resource_name=resource_name,
        cost=total_cost,
        usage_type=UsageType.TOOL_CALL,
        quantity=quantity,
        metadata={
            "provider": provider,
            "audio_seconds": audio_seconds,
            "kind": "stt",
            **(dict(metadata) if metadata else {}),
        },
        cost_origin=cost_origin,
    )


async def record_tts_usage(
    *,
    user: User,
    company: Company,
    provider: str,
    char_count: int,
    metadata: Mapping[str, Any] | None = None,
    cost_origin: str = COST_ORIGIN_PLATFORM,
) -> str:
    """Записать списание за TTS-вызов; при ``cost_origin=company`` cost=0."""
    if not provider or not isinstance(provider, str):
        raise ValueError("voice_usage.record_tts_usage: provider обязателен.")
    if char_count < 0:
        raise ValueError("voice_usage.record_tts_usage: char_count < 0.")

    user_obj, company_obj = _resolve_actor(user=user, company=company)
    quantity = max(1, int(char_count))
    is_company = cost_origin == COST_ORIGIN_COMPANY
    resource_name = "tts:byok" if is_company else f"tts:{provider}"

    billing = get_billing_service()
    if is_company:
        total_cost = 0.0
    else:
        unit_cost = await billing.get_resource_cost_for_company(company_obj, resource_name)
        total_cost = unit_cost * quantity

    return await billing.record_usage(
        user=user_obj,
        company=company_obj,
        resource_name=resource_name,
        cost=total_cost,
        usage_type=UsageType.TOOL_CALL,
        quantity=quantity,
        metadata={
            "provider": provider,
            "char_count": char_count,
            "kind": "tts",
            **(dict(metadata) if metadata else {}),
        },
        cost_origin=cost_origin,
    )


__all__ = ["record_stt_usage", "record_tts_usage"]
