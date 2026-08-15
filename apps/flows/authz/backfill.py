"""Backfill OpenFGA tuples for flows / branches / tools."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Mapping
from typing import cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from apps.flows.authz.tuples import (
    flow_branch_company_viewer_tuple,
    flow_branch_flow_link,
    flow_branch_group_viewer_tuple,
    flow_company_link,
    flow_company_viewer_tuple,
    flow_group_viewer_tuple,
    flow_platform_link,
    flow_ui_share_flow_link,
    flow_ui_share_owner_tuple,
    flow_ui_share_public_editor_tuple,
    flow_ui_share_public_viewer_tuple,
    tool_company_link,
    tool_company_viewer_tuple,
    tool_group_viewer_tuple,
    tool_platform_link,
)
from apps.flows.src.models.flow_config import FlowConfig
from apps.flows.src.models.tool_reference import ToolReference
from core.authz.factory import build_authz_service
from core.authz.models import AuthzObject, AuthzTuple
from core.authz.platform_sync import ensure_platform_global_admin
from core.authz.service import AuthzService
from core.authz.types import AuthzObjectType, AuthzRelation
from core.config import get_settings
from core.db.storage import Storage
from core.logging import get_logger
from core.types import parse_json_object

logger = get_logger(__name__)

_OPENFGA_WRITE_CHUNK = 100


def _compound_object_key_is_unscoped(
    object_type: AuthzObjectType, object_key: str
) -> bool:
    if object_type in (AuthzObjectType.FLOW, AuthzObjectType.TOOL):
        return "/" not in object_key
    if object_type is AuthzObjectType.FLOW_BRANCH:
        return object_key.count("/") != 2
    raise ValueError(f"not a compound flow object type: {object_type}")


async def _delete_unscoped_compound_tuples(
    authz: AuthzService, object_type: AuthzObjectType
) -> int:
    tuples = await authz.list_tuples(object_type=object_type)
    deletes = [
        item
        for item in tuples
        if _compound_object_key_is_unscoped(object_type, item.obj.object_key)
    ]
    for start in range(0, len(deletes), _OPENFGA_WRITE_CHUNK):
        await authz.delete(deletes[start : start + _OPENFGA_WRITE_CHUNK])
    return len(deletes)


def _flow_permission_writes(
    flow_id: str, company_id: str, permission: list[str]
) -> list[AuthzTuple]:
    groups = [item.strip() for item in permission if item.strip()]
    if not groups:
        return [flow_company_viewer_tuple(flow_id, company_id)]
    return [
        flow_group_viewer_tuple(flow_id, group_name, company_id=company_id)
        for group_name in groups
    ]


def _branch_permission_writes(
    flow_id: str,
    branch_id: str,
    company_id: str,
    permission: list[str],
) -> list[AuthzTuple]:
    writes: list[AuthzTuple] = [
        flow_branch_flow_link(flow_id, branch_id, company_id=company_id)
    ]
    if not permission:
        return writes
    groups = [item.strip() for item in permission if item.strip()]
    if not groups:
        writes.append(flow_branch_company_viewer_tuple(flow_id, branch_id, company_id))
    else:
        writes.extend(
            flow_branch_group_viewer_tuple(
                flow_id, branch_id, group_name, company_id=company_id
            )
            for group_name in groups
        )
    return writes


def _tool_permission_writes(
    tool_id: str, company_id: str, permission: list[str]
) -> list[AuthzTuple]:
    writes: list[AuthzTuple] = [
        tool_company_link(tool_id, company_id),
        tool_platform_link(tool_id, company_id=company_id),
    ]
    groups = [item.strip() for item in permission if item.strip()]
    if not groups:
        writes.append(tool_company_viewer_tuple(tool_id, company_id))
    else:
        writes.extend(
            tool_group_viewer_tuple(tool_id, group_name, company_id=company_id)
            for group_name in groups
        )
    return writes


def _parse_company_resource_key(storage_key: str, resource: str) -> tuple[str, str] | None:
    # company:{company_id}:flow:{flow_id} / company:{company_id}:tool:{tool_id}
    parts = storage_key.split(":")
    if len(parts) < 4 or parts[0] != "company" or parts[2] != resource:
        return None
    company_id = parts[1]
    entity_id = parts[3]
    if not company_id or not entity_id:
        return None
    return company_id, entity_id


async def backfill_flows_authz(*, limit: int | None = None) -> tuple[int, int, int]:
    settings = get_settings()
    if not settings.openfga.enabled:
        raise RuntimeError("openfga.enabled must be true for flows authz backfill")
    if not settings.database.flows_url:
        raise RuntimeError("database.flows_url is required for flows authz backfill")

    authz = build_authz_service()
    if not authz.enabled:
        raise RuntimeError("openfga.enabled must be true for flows authz backfill")

    await ensure_platform_global_admin(authz)
    unscoped_flows = await _delete_unscoped_compound_tuples(
        authz, AuthzObjectType.FLOW
    )
    unscoped_tools = await _delete_unscoped_compound_tuples(
        authz, AuthzObjectType.TOOL
    )
    unscoped_branches = await _delete_unscoped_compound_tuples(
        authz, AuthzObjectType.FLOW_BRANCH
    )
    logger.info(
        "flows authz backfill purged unscoped flows=%s tools=%s branches=%s",
        unscoped_flows,
        unscoped_tools,
        unscoped_branches,
    )

    storage = Storage(db_url=str(settings.database.flows_url))
    flows_written = 0
    tools_written = 0
    shares_written = 0
    try:
        flow_rows = await storage.get_all_by_prefix("company:", limit=50_000)
        for storage_key, raw_value in flow_rows.items():
            if limit is not None and flows_written + tools_written + shares_written >= limit:
                break
            parsed = _parse_company_resource_key(storage_key, "flow")
            if parsed is None:
                continue
            company_id, flow_id = parsed
            payload = parse_json_object(raw_value, "flow_config")
            config = FlowConfig.model_validate(payload)
            if config.flow_id != flow_id:
                raise ValueError(
                    f"flow_id mismatch in key {storage_key}: {config.flow_id!r}"
                )
            flow_desired = [
                flow_company_link(flow_id, company_id),
                flow_platform_link(flow_id, company_id=company_id),
                *_flow_permission_writes(flow_id, company_id, config.permission),
            ]
            flow_existing = await authz.list_tuples(
                AuthzObject.flow(flow_id, company_id=company_id)
            )
            flow_desired_set = frozenset(flow_desired)
            flow_existing_set = frozenset(flow_existing)
            await authz.write_and_delete(
                list(flow_desired_set - flow_existing_set),
                [
                    item
                    for item in flow_existing_set - flow_desired_set
                    if item.relation is not AuthzRelation.OWNER
                ],
            )
            for branch_id, branch in config.branches.items():
                branch_desired = _branch_permission_writes(
                    flow_id, branch_id, company_id, branch.permission
                )
                branch_existing = await authz.list_tuples(
                    AuthzObject.flow_branch(flow_id, branch_id, company_id=company_id)
                )
                branch_desired_set = frozenset(branch_desired)
                branch_existing_set = frozenset(branch_existing)
                await authz.write_and_delete(
                    list(branch_desired_set - branch_existing_set),
                    list(branch_existing_set - branch_desired_set),
                )
            flows_written += 1

        tool_rows = await storage.get_all_by_prefix("company:", limit=50_000)
        for storage_key, raw_value in tool_rows.items():
            if limit is not None and flows_written + tools_written + shares_written >= limit:
                break
            parsed = _parse_company_resource_key(storage_key, "tool")
            if parsed is None:
                continue
            company_id, tool_id = parsed
            payload = parse_json_object(raw_value, "tool_reference")
            tool = ToolReference.model_validate(payload)
            if tool.tool_id != tool_id:
                raise ValueError(
                    f"tool_id mismatch in key {storage_key}: {tool.tool_id!r}"
                )
            tool_desired = _tool_permission_writes(
                tool_id, company_id, tool.permission
            )
            tool_existing = await authz.list_tuples(
                AuthzObject.tool(tool_id, company_id=company_id)
            )
            tool_desired_set = frozenset(tool_desired)
            tool_existing_set = frozenset(tool_existing)
            await authz.write_and_delete(
                list(tool_desired_set - tool_existing_set),
                list(tool_existing_set - tool_desired_set),
            )
            tools_written += 1

        engine = create_async_engine(str(settings.database.flows_url))
        share_rows: list[Mapping[str, object]] = []
        try:
            async with engine.connect() as connection:
                share_sql = (
                    "SELECT grant_id, flow_id, company_id, created_by_user_id, permission "
                    "FROM flow_ui_share_grants "
                    "WHERE revoked_at IS NULL "
                    "ORDER BY grant_id"
                )
                remaining: int | None = None
                if limit is not None:
                    remaining = limit - flows_written - tools_written - shares_written
                if remaining is None:
                    result = await connection.execute(text(share_sql))
                    share_rows = [
                        cast(Mapping[str, object], dict(row))
                        for row in result.mappings()
                    ]
                elif remaining > 0:
                    result = await connection.execute(
                        text(f"{share_sql} LIMIT :share_limit"),
                        {"share_limit": remaining},
                    )
                    share_rows = [
                        cast(Mapping[str, object], dict(row))
                        for row in result.mappings()
                    ]
        finally:
            await engine.dispose()

        for row in share_rows:
            grant_id = cast(str, row["grant_id"])
            flow_id = cast(str, row["flow_id"])
            company_id = cast(str, row["company_id"])
            owner_user_id = cast(str, row["created_by_user_id"])
            permission = cast(str, row["permission"])
            writes = [
                flow_ui_share_flow_link(grant_id, flow_id, company_id=company_id),
                flow_ui_share_owner_tuple(grant_id, owner_user_id),
            ]
            if permission == "editor":
                writes.append(flow_ui_share_public_editor_tuple(grant_id))
            elif permission == "viewer":
                writes.append(flow_ui_share_public_viewer_tuple(grant_id))
            else:
                logger.error(
                    "flows authz backfill skip share grant_id=%s permission=%s (wire is viewer|editor)",
                    grant_id,
                    permission,
                )
                continue
            await authz.write(writes)
            shares_written += 1
    finally:
        await authz.close()

    logger.info(
        "flows authz backfill complete flows=%s tools=%s shares=%s",
        flows_written,
        tools_written,
        shares_written,
    )
    return flows_written, tools_written, shares_written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill flows/tools into OpenFGA")
    _ = parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    limit = cast(int | None, args.limit)
    flows_written, tools_written, shares_written = asyncio.run(
        backfill_flows_authz(limit=limit)
    )
    _ = sys.stdout.write(
        f"flows={flows_written} tools={tools_written} shares={shares_written}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
