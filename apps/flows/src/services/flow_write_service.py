"""Запись текущей версии flow: optimistic concurrency и persist."""

from __future__ import annotations

from apps.flows.config import get_settings
from apps.flows.src.flow_ui.problems import assert_flow_ui_publishable
from apps.flows.src.models.flow_api import FlowCreateRequest
from apps.flows.src.models.flow_config import BranchConfig, FlowConfig, FlowVariableConfig
from apps.flows.src.services.flow_access_service import FlowAccessService
from apps.flows.src.services.flow_employee_provisioning import sync_flow_employee
from core.authz.service import AuthzService
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from core.events import publish_event_to_user
from core.mail.service import MailService
from core.request_scope import require_company
from core.types import JsonObject
from core.ui_document.document import FlowUIDocument


def _check_base_version(current_version: str, base_version: str | None) -> None:
    if base_version is None or base_version == "":
        return
    if base_version != current_version:
        raise PlatformConflictError(
            "flow version conflict",
            error_code="flow_version_conflict",
            error_params={
                "base_version": base_version,
                "current_version": current_version,
            },
        )


class FlowWriteService:
    """Сценарий замены текущей версии flow."""

    def __init__(
        self,
        flow_access_service: FlowAccessService,
        authz_service: AuthzService,
        mail_service: MailService,
    ) -> None:
        self._flow_access_service: FlowAccessService = flow_access_service
        self._authz_service: AuthzService = authz_service
        self._mail_service: MailService = mail_service

    async def replace_current(
        self,
        payload: FlowCreateRequest,
        *,
        nodes: dict[str, JsonObject],
        variables: dict[str, FlowVariableConfig],
        branches: dict[str, BranchConfig],
    ) -> FlowConfig:
        existing = await FlowConfig.current_for_flow(payload.flow_id)
        if existing is None:
            raise PlatformNotFoundError("Flow not found")
        _check_base_version(existing.version, payload.base_version)
        speech_merged = payload.speech if payload.speech is not None else existing.speech
        interface_merged = payload.interface if payload.interface is not None else existing.interface
        self._assert_publishable(interface_merged, branches)
        description = payload.description if payload.description is not None else ""
        flow_config = FlowConfig(
            flow_id=payload.flow_id,
            name=payload.name,
            description=description,
            entry=payload.entry,
            nodes=nodes,
            edges=payload.edges,
            variables=variables,
            tags=payload.tags,
            branches=branches,
            source=existing.source,
            triggers=payload.triggers,
            resources=payload.resources,
            metadata=existing.metadata,
            store_card_image_url=payload.store_card_image_url,
            speech=speech_merged,
            interface=interface_merged,
            employee=payload.employee,
        )
        await self._persist(flow_config)
        await sync_flow_employee(self._authz_service, self._mail_service, flow_config)
        scope = require_company()
        await publish_event_to_user(
            user_id=scope.user_id,
            type="flows/flow/updated",
            payload={"flow_id": payload.flow_id, "version": flow_config.version},
        )
        return flow_config

    def _assert_publishable(
        self,
        interface: FlowUIDocument,
        branches: dict[str, BranchConfig],
    ) -> None:
        limits = get_settings().flow_ui
        assert_flow_ui_publishable(interface, limits)
        for branch_cfg in branches.values():
            if branch_cfg.interface is not None:
                assert_flow_ui_publishable(branch_cfg.interface, limits)

    async def _persist(self, flow_config: FlowConfig) -> None:
        previous = await FlowConfig.current_for_flow(flow_config.flow_id)
        _ = await FlowConfig.create_version(flow_config)
        try:
            scope = require_company()
            await self._flow_access_service.sync_flow_saved(
                flow_config,
                company_id=scope.company_id,
                owner_user_id=scope.user_id,
            )
        except Exception:
            if previous is None:
                _ = await FlowConfig.delete_by_flow_id(flow_config.flow_id)
            else:
                _ = await FlowConfig.create_version(previous)
            raise
