"""Lazy install public-bundle в активную компанию при первом обращении к flow_id.

Публичные bundle копируются компаниям в company_init; агент, добавленный в
registry позже, доезжает сюда — A2A get-config и employee inbox.
"""

from __future__ import annotations

from pathlib import Path

from apps.flows.src.models.bundle_registry import FlowBundleRegistry
from apps.flows.src.models.flow_config import FlowConfig
from apps.flows.src.services.flow_access_service import FlowAccessService
from apps.flows.src.services.flows_loader import FlowsLoader
from core.authz.service import AuthzService
from core.files.service import FilesService
from core.mail.service import MailService
from core.types import parse_yaml_value, require_json_object


async def materialize_public_bundle(
    *,
    flow_id: str,
    flow_access_service: FlowAccessService,
    files_service: FilesService,
    authz_service: AuthzService,
    mail_service: MailService,
) -> FlowConfig | None:
    """Загружает public-bundle ``flow_id`` в активную компанию; иначе ``None``."""
    flows_root = Path(__file__).resolve().parents[2]
    registry_path = flows_root / "registry.yaml"
    if not registry_path.exists():
        return None
    loaded = parse_yaml_value(registry_path.read_text(encoding="utf-8"), "registry.yaml")
    registry = FlowBundleRegistry.model_validate(
        require_json_object(loaded, "registry.yaml") if loaded is not None else {}
    )
    entry = next((item for item in registry.flows if item.id == flow_id), None)
    if entry is None or not entry.public:
        return None
    loader = FlowsLoader(
        bundles_dir=flows_root / "bundles",
        registry_path=registry_path,
        flow_access_service=flow_access_service,
        files_service=files_service,
        authz_service=authz_service,
        mail_service=mail_service,
    )
    try:
        _ = await loader.reload_flow_bundle(flow_id)
    except ValueError:
        return None
    return await FlowConfig.current_for_flow(flow_id)
