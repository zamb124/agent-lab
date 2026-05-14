"""
Синхронизация в development: flows с landing_public_demo в registry.yaml перезаписываются в БД с диска.

Источник id — только registry (флаг landing_public_demo: true), без списков в коде.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from apps.flows.config import FlowSettings
from apps.flows.src.container import FlowContainer
from apps.flows.src.services.flows_loader import FlowsLoader
from core.context import clear_context, set_context
from core.logging import get_logger
from core.models.context_models import Context, Language
from core.models.identity_models import Company, User

logger = get_logger(__name__)


def landing_public_demo_bundle_ids_from_registry(registry_path: Path) -> tuple[str, ...]:
    if not registry_path.is_file():
        return ()
    with open(registry_path, "r", encoding="utf-8") as f:
        reg = yaml.safe_load(f) or {}
    flows = reg.get("flows") or []
    out: list[str] = []
    for entry in flows:
        if not isinstance(entry, dict):
            continue
        if entry.get("landing_public_demo") is not True:
            continue
        fid = entry.get("id")
        if isinstance(fid, str) and fid.strip():
            out.append(fid.strip())
    return tuple(out)


async def sync_landing_public_demo_flows_from_bundles(container: FlowContainer, settings: FlowSettings) -> None:
    if settings.server.env != "development":
        return

    registry_path = Path(__file__).resolve().parents[2] / "registry.yaml"
    bundles_dir = Path(__file__).resolve().parents[2] / "bundles"
    bundle_ids = landing_public_demo_bundle_ids_from_registry(registry_path)
    if not bundle_ids:
        logger.info(
            "flows.landing_demo_bundle_sync_skipped",
            reason="no_entries_with_landing_public_demo_in_registry",
        )
        return

    system_context = Context(
        user=User(user_id="system", name="System", groups=["admin"]),
        host="system",
        session_id="landing-bundle-dev-sync",
        channel="system",
        language=Language.RU,
        active_company=Company(
            company_id="system",
            name="System",
            subdomain="system",
        ),
        user_companies=[],
        trace_id="system:landing_bundle_dev_sync",
    )
    set_context(system_context)
    try:
        loader = FlowsLoader(
            bundles_dir=bundles_dir,
            flow_repository=container.flow_repository,
            node_repository=container.node_repository,
            tool_repository=container.tool_repository,
            registry_path=registry_path,
        )
        for bundle_id in bundle_ids:
            try:
                await loader.reload_flow_bundle(bundle_id)
                logger.info(
                    "flows.landing_demo_bundle_synced",
                    bundle_id=bundle_id,
                )
            except Exception as e:
                logger.warning(
                    "flows.landing_demo_bundle_sync_failed",
                    bundle_id=bundle_id,
                    exception_message=str(e),
                    exc_info=True,
                )
    finally:
        clear_context()
