"""
Автосинхронизация интеграций namespace: создание/отмена расписаний platform scheduler.
"""

from __future__ import annotations

from datetime import datetime
from typing import cast
from zoneinfo import ZoneInfo

from croniter import CroniterBadCronError, croniter

from apps.crm.integrations.registry import IntegrationRegistry
from apps.crm.scheduled_integration_constants import (
    SCHEDULED_NAMESPACE_INTEGRATION_UNIFIED_SYNC_TASK_NAME,
)
from core.clients.scheduler_client import SchedulerClient
from core.db.repositories.namespace_repository import NamespaceRepository
from core.integrations.models import IntegrationProvider
from core.integrations.oauth_service import OAuthService
from core.models.identity_models import Namespace, NamespaceCRMSettings
from core.scheduler.models import PlatformScheduleCreateRequest, PlatformScheduleType


def validate_cron_for_timezone(cron: str, timezone_name: str) -> None:
    """Падает ValueError если выражение cron несовместимо с croniter в данной таймзоне."""
    raw = cron.strip()
    if not raw:
        raise ValueError("cron не может быть пустым")
    tz_name = timezone_name.strip()
    if not tz_name:
        raise ValueError("timezone не может быть пустым")
    try:
        zi = ZoneInfo(tz_name)
    except Exception as exc:
        raise ValueError(f"Неизвестная timezone: {timezone_name}") from exc
    base = datetime.now(zi)
    try:
        _ = croniter(raw, base)
    except CroniterBadCronError as exc:
        raise ValueError(f"Некорректное выражение cron: {exc}") from exc


class IntegrationAutoSyncService:
    def __init__(
        self,
        *,
        namespace_repository: NamespaceRepository,
        integration_registry: IntegrationRegistry,
        oauth_service: OAuthService,
        scheduler_client: SchedulerClient,
    ) -> None:
        self._namespace_repository: NamespaceRepository = namespace_repository
        self._integration_registry: IntegrationRegistry = integration_registry
        self._oauth_service: OAuthService = oauth_service
        self._scheduler_client: SchedulerClient = scheduler_client

    async def _assert_token_for_integration(
        self,
        *,
        company_id: str,
        oauth_user_id: str,
        namespace_name: str,
        provider_id: str,
    ) -> None:
        connector = self._integration_registry.get(provider_id)
        prov = connector.integration_provider
        if prov == IntegrationProvider.AMOCRM:
            cred = await self._oauth_service.get_valid_token(
                company_id=company_id,
                user_id=oauth_user_id,
                provider=IntegrationProvider.AMOCRM,
                service=f"amocrm:{namespace_name}",
            )
            if cred is None:
                raise ValueError(
                    "Интеграция не подключена для выбранного пользователя OAuth: подключите AmoCRM"
                )
            return
        raise ValueError(f"Автосинхронизация для провайдера «{provider_id}» не настроена")

    async def apply_integration_auto_sync(
        self,
        *,
        company_id: str,
        acting_user_id: str,
        namespace_name: str,
        provider_id: str,
        auto_sync_enabled: bool,
        auto_sync_cron: str | None,
        auto_sync_timezone: str | None,
    ) -> Namespace:
        ns_raw = namespace_name.strip()
        pid = provider_id.strip()
        if not ns_raw:
            raise ValueError("namespace_name обязателен")
        if not pid:
            raise ValueError("provider_id обязателен")

        _ = self._integration_registry.get(pid)

        existing = await self._namespace_repository.get(ns_raw)
        if existing is None or existing.company_id != company_id:
            raise ValueError("namespace not found")

        crm = existing.crm_settings
        if crm is None:
            crm = NamespaceCRMSettings()
        integ = cast(dict[str, dict[str, object]], crm.integrations.copy())
        raw_block = integ.get(pid)
        block: dict[str, object] = dict(raw_block) if raw_block is not None else {}

        tz = (auto_sync_timezone or "UTC").strip()
        if not auto_sync_enabled:
            sid = block.get("auto_sync_schedule_task_id")
            if isinstance(sid, str) and sid.strip():
                _ = await self._scheduler_client.cancel_schedule(sid.strip())
            block["auto_sync_enabled"] = False
            block["auto_sync_schedule_task_id"] = None
            integ[pid] = block
            existing.crm_settings = crm.model_copy(update={"integrations": integ})
            _ = await self._namespace_repository.set(existing)
            return existing

        cron_raw = auto_sync_cron if isinstance(auto_sync_cron, str) else ""
        if not cron_raw.strip():
            raise ValueError("При включённом автосинке поле cron обязательно")
        cron = cron_raw.strip()
        validate_cron_for_timezone(cron, tz)

        oauth_actor = block.get("auto_sync_oauth_user_id")
        if isinstance(oauth_actor, str) and oauth_actor.strip():
            oauth_user = oauth_actor.strip()
        else:
            oauth_user = acting_user_id.strip()
        if not oauth_user:
            raise ValueError("Не удалось определить пользователя OAuth для автосинка")

        await self._assert_token_for_integration(
            company_id=company_id,
            oauth_user_id=oauth_user,
            namespace_name=ns_raw,
            provider_id=pid,
        )

        prev_enabled = bool(block.get("auto_sync_enabled"))
        old_cron = block.get("auto_sync_cron")
        old_tz = block.get("auto_sync_timezone")
        old_sid = block.get("auto_sync_schedule_task_id")

        old_cron_s = old_cron.strip() if isinstance(old_cron, str) else ""
        old_tz_s = old_tz.strip() if isinstance(old_tz, str) and old_tz.strip() else "UTC"

        need_new_schedule = (
            not isinstance(old_sid, str)
            or not old_sid.strip()
            or not prev_enabled
            or old_cron_s != cron
            or old_tz_s != tz
        )

        if need_new_schedule and isinstance(old_sid, str) and old_sid.strip():
            _ = await self._scheduler_client.cancel_schedule(old_sid.strip())

        new_schedule_id: str
        if need_new_schedule:
            req = PlatformScheduleCreateRequest(
                target_service="crm",
                task_name=SCHEDULED_NAMESPACE_INTEGRATION_UNIFIED_SYNC_TASK_NAME,
                queue_name="crm",
                schedule_type=PlatformScheduleType.CRON,
                cron=cron,
                timezone=tz,
                payload={
                    "namespace": ns_raw,
                    "provider_id": pid,
                    "oauth_user_id": oauth_user,
                },
            )
            created = await self._scheduler_client.create_schedule(req)
            new_schedule_id = created.id
        else:
            new_schedule_id = str(old_sid).strip()

        block["auto_sync_enabled"] = True
        block["auto_sync_cron"] = cron
        block["auto_sync_timezone"] = tz
        block["auto_sync_oauth_user_id"] = oauth_user
        block["auto_sync_schedule_task_id"] = new_schedule_id
        integ[pid] = block
        existing.crm_settings = crm.model_copy(update={"integrations": integ})
        _ = await self._namespace_repository.set(existing)
        return existing

    async def apply_auto_note_ai_analyze(
        self,
        *,
        company_id: str,
        namespace_name: str,
        provider_id: str,
        auto_note_ai_analyze: bool,
    ) -> Namespace:
        ns_raw = namespace_name.strip()
        pid = provider_id.strip()
        if not ns_raw:
            raise ValueError("namespace_name обязателен")
        if not pid:
            raise ValueError("provider_id обязателен")

        _ = self._integration_registry.get(pid)

        existing = await self._namespace_repository.get(ns_raw)
        if existing is None or existing.company_id != company_id:
            raise ValueError("namespace not found")

        crm = existing.crm_settings
        if crm is None:
            crm = NamespaceCRMSettings()
        integ = cast(dict[str, dict[str, object]], crm.integrations.copy())
        raw_block = integ.get(pid)
        block: dict[str, object] = dict(raw_block) if raw_block is not None else {}
        block["auto_note_ai_analyze"] = bool(auto_note_ai_analyze)
        integ[pid] = block
        existing.crm_settings = crm.model_copy(update={"integrations": integ})
        _ = await self._namespace_repository.set(existing)
        return existing
