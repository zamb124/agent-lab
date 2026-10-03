"""Backfill CRM OpenFGA tuples from live crm_entities (grants dual-written at runtime)."""

from __future__ import annotations

import asyncio
import sys

from apps.crm.authz.tuples import (
    crm_entity_namespace_link,
    crm_entity_owner_tuple,
    crm_namespace_company_editor_tuple,
    crm_namespace_company_link,
    crm_namespace_company_viewer_tuple,
)
from apps.crm.config import get_crm_settings
from apps.crm.di import CrmDi
from apps.crm.models.crm_entity import CRMEntity
from core.authz.backfill_limit import parse_backfill_limit
from core.authz.service import AuthzService
from core.di import open_di
from core.di.kit import ProcessIdentity
from core.files.urls import resolve_files_route_segment
from core.logging import get_logger

logger = get_logger(__name__)

async def _backfill_entities(authz: AuthzService, *, limit: int | None) -> int:
    if not authz.enabled:
        raise RuntimeError("openfga.enabled must be true for CRM authz backfill")

    written = 0
    rows = await CRMEntity.all_ordered_by_created_at()

    for row in rows:
        if limit is not None and written >= limit:
            break
        entity_id = row.entity_id
        company_id = row.company_id
        namespace = row.namespace
        user_id = row.user_id
        if entity_id == "":
            raise ValueError("backfill entity_id is required")
        if company_id == "":
            raise ValueError(f"backfill company_id is required: {entity_id}")
        if namespace == "":
            raise ValueError(f"backfill namespace is required: {entity_id}")
        if user_id == "":
            raise ValueError(f"backfill entity missing user_id: {entity_id}")
        await authz.write(
            [
                crm_namespace_company_link(company_id, namespace),
                crm_namespace_company_viewer_tuple(company_id, namespace),
                crm_namespace_company_editor_tuple(company_id, namespace),
                crm_entity_owner_tuple(entity_id, user_id),
                crm_entity_namespace_link(entity_id, company_id, namespace),
            ]
        )
        written += 1
    logger.info("crm.entity.backfill.complete.entities", entities=written)
    return written


async def backfill_crm_authz(*, limit: int | None = None) -> int:
    settings = get_crm_settings()
    if not settings.openfga.enabled:
        raise RuntimeError("openfga.enabled must be true for CRM authz backfill")
    async with open_di(
        CrmDi,
        settings=settings,
        identity=ProcessIdentity(
            service_name="crm",
            files_route_segment=resolve_files_route_segment("crm"),
        ),
        database="crm_url",
    ) as di:
        return await _backfill_entities(di.authz_service, limit=limit)


def main(argv: list[str] | None = None) -> int:
    limit = parse_backfill_limit("Backfill CRM OpenFGA tuples", argv)
    entities = asyncio.run(backfill_crm_authz(limit=limit))
    _ = sys.stdout.write(f"entities={entities}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
