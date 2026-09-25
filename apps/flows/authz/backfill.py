"""Backfill OpenFGA tuples for flows / branches / tools."""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import cast

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
from core.db.oxyde_runtime import init_oxyde_databases
from core.logging import get_logger
from core.models.flow_ui_share import FlowUIShareGrant

logger = get_logger(__name__)

_OPENFGA_WRITE_CHUNK = 100
_KV_PAGE_SIZE = 5000


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


async def _write_tuple_chunks(authz: AuthzService, tuples: list[AuthzTuple]) -> None:
    total = len(tuples)
    for start in range(0, total, _OPENFGA_WRITE_CHUNK):
        await authz.write(tuples[start : start + _OPENFGA_WRITE_CHUNK])
        done = min(start + _OPENFGA_WRITE_CHUNK, total)
        if done == total or done % 10000 == 0:
            logger.info("flows.authz.backfill.tuples.written", written=done, total=total)


async def _delete_tuple_chunks(authz: AuthzService, tuples: list[AuthzTuple]) -> None:
    total = len(tuples)
    for start in range(0, total, _OPENFGA_WRITE_CHUNK):
        await authz.delete(tuples[start : start + _OPENFGA_WRITE_CHUNK])
        done = min(start + _OPENFGA_WRITE_CHUNK, total)
        if done == total or done % 10000 == 0:
            logger.info("flows.authz.backfill.tuples.deleted", deleted=done, total=total)


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


async def backfill_flows_authz(*, limit: int | None = None) -> tuple[int, int, int]:
    settings = get_settings()
    if not settings.openfga.enabled:
        raise RuntimeError("openfga.enabled must be true for flows authz backfill")
    if settings.database.flows_url is None or settings.database.flows_url == "":
        raise RuntimeError("database.flows_url is required for flows authz backfill")
    if settings.database.shared_url is None or settings.database.shared_url == "":
        raise RuntimeError("database.shared_url is required for flows authz backfill")
    await init_oxyde_databases(
        default_url=settings.database.flows_url,
        shared_url=settings.database.shared_url,
    )

    authz = build_authz_service()
    if not authz.enabled:
        raise RuntimeError("openfga.enabled must be true for flows authz backfill")

    await ensure_platform_global_admin(authz)
    unscoped_flows = await _delete_unscoped_compound_tuples(
        authz, AuthzObjectType.FLOW
    )
    unscoped_branches = await _delete_unscoped_compound_tuples(
        authz, AuthzObjectType.FLOW_BRANCH
    )
    logger.info("flows.authz.backfill.purged.unscoped", flows=unscoped_flows, branches=unscoped_branches)

    flows_written = 0
    tools_written = 0
    shares_written = 0
    try:
        flow_offset = 0
        stop_flows = False
        while not stop_flows:
            flow_page = await FlowConfig.list_current(limit=_KV_PAGE_SIZE, offset=flow_offset)
            if len(flow_page) == 0:
                break
            for config in flow_page:
                if limit is not None and flows_written + tools_written + shares_written >= limit:
                    stop_flows = True
                    break
                company_id = config.company_id
                flow_id = config.flow_id
                if company_id == "" or flow_id == "":
                    raise ValueError("flow row requires company_id and flow_id")
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
            if len(flow_page) < _KV_PAGE_SIZE:
                break
            flow_offset += _KV_PAGE_SIZE
        logger.info("flows.authz.backfill.flows.written", written=flows_written)

        tool_desired_all: list[AuthzTuple] = []
        tool_offset = 0
        stop_tools = False
        while not stop_tools:
            tool_page = await ToolReference.list_in_tool_id_order(
                limit=_KV_PAGE_SIZE,
                offset=tool_offset,
            )
            if len(tool_page) == 0:
                break
            for tool in tool_page:
                if limit is not None and flows_written + tools_written + shares_written >= limit:
                    stop_tools = True
                    break
                company_id = tool.company_id
                tool_id = tool.tool_id
                if company_id == "" or tool_id == "":
                    raise ValueError("tool row requires company_id and tool_id")
                permission = tool.permission
                tool_desired_all.extend(
                    _tool_permission_writes(tool_id, company_id, permission)
                )
                tools_written += 1
                if tools_written % 20000 == 0:
                    logger.info("flows.authz.backfill.tools.scanned", scanned=tools_written)
            if len(tool_page) < _KV_PAGE_SIZE:
                break
            tool_offset += _KV_PAGE_SIZE
        logger.info("flows.authz.backfill.tools.loaded", loaded=tools_written, desired_tuples=len(tool_desired_all))
        unscoped_tools = 0
        if limit is None:
            unscoped_tools = await _delete_unscoped_compound_tuples(
                authz, AuthzObjectType.TOOL
            )
        logger.info("flows.authz.backfill.purged.unscoped", tools=unscoped_tools)
        tool_desired_set = frozenset(tool_desired_all)
        if limit is None:
            tool_existing = await authz.list_tuples(object_type=AuthzObjectType.TOOL)
            tool_existing_set = frozenset(tool_existing)
            await _write_tuple_chunks(authz, list(tool_desired_set - tool_existing_set))
            await _delete_tuple_chunks(
                authz, list(tool_existing_set - tool_desired_set)
            )
        else:
            await _write_tuple_chunks(authz, list(tool_desired_set))

        remaining: int | None = None
        if limit is not None:
            remaining = limit - flows_written - tools_written - shares_written
        grants = await FlowUIShareGrant.list_unrevoked(limit=remaining)
        for grant in grants:
            writes = [
                flow_ui_share_flow_link(grant.grant_id, grant.flow_id, company_id=grant.company_id),
                flow_ui_share_owner_tuple(grant.grant_id, grant.created_by_user_id),
            ]
            if grant.permission == "editor":
                writes.append(flow_ui_share_public_editor_tuple(grant.grant_id))
            else:
                writes.append(flow_ui_share_public_viewer_tuple(grant.grant_id))
            await authz.write(writes)
            shares_written += 1
    finally:
        await authz.close()

    logger.info(
        "flows.authz.backfill.complete.flows",
        flows=flows_written,
        tools=tools_written,
        shares=shares_written,
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
