"""
Автосинхронизация интеграций namespace: создание/отмена расписаний platform scheduler.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import CroniterBadCronError, croniter

from apps.crm.integrations.registry import IntegrationRegistry
from apps.crm.tasks.task_names import SCHEDULED_NAMESPACE_INTEGRATION_UNIFIED_SYNC
from core.clients.scheduler_client import SchedulerClient
from core.integrations.models import IntegrationProvider
from core.integrations.oauth_service import OAuthService
from core.models.identity_models import Namespace, NamespaceCRMSettings
from core.namespace import NamespaceService
from core.scheduler.models import PlatformScheduleCreateRequest, PlatformScheduleType
from core.types import JsonObject


def _copied_integrations(crm: NamespaceCRMSettings) -> dict[str, JsonObject]:
    return {provider_id: dict(block) for provider_id, block in crm.integrations.items()}


def _integration_block(blocks: dict[str, JsonObject], provider_id: str) -> JsonObject:
    current = blocks.get(provider_id)
    if current is None:
        empty: JsonObject = {}
        return empty
    return dict(current)


def validate_cron_for_timezone(cron: str, timezone_name: str) -> None:
    """Падает ValueError если выражение cron несовместимо с croniter в данной таймзоне."""
    raw = cron.strip()
    if not raw:
        raise ValueError("cron must not be empty")
    tz_name = timezone_name.strip()
    if not tz_name:
        raise ValueError("timezone must not be empty")
    try:
        zi = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown timezone: {timezone_name}") from exc
    base = datetime.now(zi)
    try:
        _ = croniter(raw, base)
    except CroniterBadCronError as exc:
        raise ValueError(f"Invalid cron expression: {exc}") from exc


class IntegrationAutoSyncService:
    def __init__(
        self,
        *,
        namespace_service: NamespaceService,
        integration_registry: IntegrationRegistry,
        oauth_service: OAuthService,
        scheduler_client: SchedulerClient,
    ) -> None:
        self._namespace_service: NamespaceService = namespace_service
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
                    "Integration is not connected for the selected OAuth user: connect AmoCRM"
                )
            return
        raise ValueError(f"Autosync for provider «{provider_id}» is not configured")

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
            raise ValueError("namespace_name is required")
        if not pid:
            raise ValueError("provider_id is required")

        _ = self._integration_registry.get(pid)

        existing = await self._namespace_service.get(ns_raw)
        if existing is None or existing.company_id != company_id:
            raise ValueError("namespace not found")

        crm = existing.crm_settings
        if crm is None:
            crm = NamespaceCRMSettings()
        integ = _copied_integrations(crm)
        block = _integration_block(integ, pid)

        if not auto_sync_enabled:
            current_schedule_task_id = block.get("auto_sync_schedule_task_id")
            if isinstance(current_schedule_task_id, str) and current_schedule_task_id.strip():
                _ = await self._scheduler_client.cancel_schedule(current_schedule_task_id.strip())
            block["auto_sync_enabled"] = False
            block["auto_sync_schedule_task_id"] = None
            integ[pid] = block
            existing.crm_settings = crm.model_copy(update={"integrations": integ})
            _ = await self._namespace_service.save(existing)
            return existing

        cron_raw = auto_sync_cron if isinstance(auto_sync_cron, str) else ""
        if not cron_raw.strip():
            raise ValueError("cron is required when autosync is enabled")
        if auto_sync_timezone is None or not auto_sync_timezone.strip():
            raise ValueError("timezone is required when autosync is enabled")
        cron = cron_raw.strip()
        tz = auto_sync_timezone.strip()
        validate_cron_for_timezone(cron, tz)

        oauth_actor = block.get("auto_sync_oauth_user_id")
        if isinstance(oauth_actor, str) and oauth_actor.strip():
            oauth_user = oauth_actor.strip()
        else:
            oauth_user = acting_user_id.strip()
        if not oauth_user:
            raise ValueError("Failed to resolve the OAuth user for autosync")

        await self._assert_token_for_integration(
            company_id=company_id,
            oauth_user_id=oauth_user,
            namespace_name=ns_raw,
            provider_id=pid,
        )

        prev_enabled = bool(block.get("auto_sync_enabled"))
        stored_cron = block.get("auto_sync_cron")
        stored_tz = block.get("auto_sync_timezone")
        stored_schedule_task_id = block.get("auto_sync_schedule_task_id")

        stored_cron_s = stored_cron.strip() if isinstance(stored_cron, str) else ""
        stored_tz_s = stored_tz.strip() if isinstance(stored_tz, str) else ""

        schedule_outdated = (
            not isinstance(stored_schedule_task_id, str)
            or not stored_schedule_task_id.strip()
            or not prev_enabled
            or stored_cron_s != cron
            or stored_tz_s != tz
        )

        if (
            schedule_outdated
            and isinstance(stored_schedule_task_id, str)
            and stored_schedule_task_id.strip()
        ):
            _ = await self._scheduler_client.cancel_schedule(stored_schedule_task_id.strip())

        active_schedule_task_id: str
        if schedule_outdated:
            req = PlatformScheduleCreateRequest(
                target_service="crm",
                task_name=SCHEDULED_NAMESPACE_INTEGRATION_UNIFIED_SYNC.name,
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
            active_schedule_task_id = created.schedule_task_id
        else:
            active_schedule_task_id = str(stored_schedule_task_id).strip()

        block["auto_sync_enabled"] = True
        block["auto_sync_cron"] = cron
        block["auto_sync_timezone"] = tz
        block["auto_sync_oauth_user_id"] = oauth_user
        block["auto_sync_schedule_task_id"] = active_schedule_task_id
        integ[pid] = block
        existing.crm_settings = crm.model_copy(update={"integrations": integ})
        _ = await self._namespace_service.save(existing)
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
            raise ValueError("namespace_name is required")
        if not pid:
            raise ValueError("provider_id is required")

        _ = self._integration_registry.get(pid)

        existing = await self._namespace_service.get(ns_raw)
        if existing is None or existing.company_id != company_id:
            raise ValueError("namespace not found")

        crm = existing.crm_settings
        if crm is None:
            crm = NamespaceCRMSettings()
        integ = _copied_integrations(crm)
        block = _integration_block(integ, pid)
        block["auto_note_ai_analyze"] = bool(auto_note_ai_analyze)
        integ[pid] = block
        existing.crm_settings = crm.model_copy(update={"integrations": integ})
        _ = await self._namespace_service.save(existing)
        return existing
