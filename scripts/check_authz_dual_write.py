#!/usr/bin/env python3
"""CI gate: ACL resource create/delete paths must dual-write OpenFGA tuples."""

from __future__ import annotations

import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

# symbol → (path relative, required substrings in same file)
_MUTATORS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "create_queue",
        "core/worktracker/service.py",
        ("sync_queue_created", "sync_queue_deleted"),
    ),
    (
        "delete_queue",
        "core/worktracker/service.py",
        ("sync_queue_deleted",),
    ),
    (
        "create",
        "apps/flows/src/services/flow_ui_share_service.py",
        ("sync_share_created", "sync_share_revoked"),
    ),
    (
        "revoke",
        "apps/flows/src/services/flow_ui_share_service.py",
        ("sync_share_revoked",),
    ),
    (
        "create_page",
        "apps/wiki/services/wiki_service.py",
        ("sync_page_created",),
    ),
    (
        "delete_page",
        "apps/wiki/services/wiki_service.py",
        ("sync_pages_deleted",),
    ),
    (
        "create_entity",
        "apps/crm/services/entity_service.py",
        ("sync_entity_created",),
    ),
    (
        "delete_entity",
        "apps/crm/services/entity_service.py",
        ("sync_entity_deleted",),
    ),
    (
        "merge_entities",
        "apps/crm/services/entity_service.py",
        ("sync_entity_created", "sync_entity_deleted"),
    ),
    (
        "get_or_create_person_entity_id",
        "apps/crm/services/user_person_service.py",
        ("sync_entity_created",),
    ),
    (
        "upsert_canonical_by_external_ref",
        "apps/crm/integrations/entity_upsert.py",
        ("sync_entity_created",),
    ),
    (
        "_copy_shallow",
        "apps/crm/services/access_request_service.py",
        ("sync_entity_created",),
    ),
    (
        "_copy_with_dependencies",
        "apps/crm/services/access_request_service.py",
        ("sync_entity_created",),
    ),
    (
        "_ensure_company_entity",
        "apps/crm/services/company_init_service.py",
        ("sync_entity_created",),
    ),
    (
        "_ensure_namespace_entity",
        "apps/crm/services/company_init_service.py",
        ("sync_entity_created",),
    ),
    (
        "create_channel",
        "apps/sync/services/channel_service.py",
        ("sync_channel_created",),
    ),
    (
        "add_member",
        "apps/sync/services/channel_service.py",
        ("set_member", "delete_channel_member"),
    ),
    (
        "sync_catalog_created",
        "apps/office/services/office_access_service.py",
        ("document_catalog_owner_tuple", "authz.write"),
    ),
    (
        "sync_catalog_deleted",
        "apps/office/services/office_access_service.py",
        ("authz.delete",),
    ),
    (
        "sync_document_created",
        "apps/office/services/office_access_service.py",
        ("document_file_owner_tuple",),
    ),
    (
        "sync_document_deleted",
        "apps/office/services/office_access_service.py",
        ("authz.delete",),
    ),
    (
        "ensure_path",
        "core/documents/tree_service.py",
        ("document_catalog_owner_tuple", "_sync_created"),
    ),
    (
        "place",
        "core/documents/tree_service.py",
        ("document_file_owner_tuple",),
    ),
    (
        "sync_flow_saved",
        "apps/flows/src/services/flow_access_service.py",
        ("authz.write",),
    ),
    (
        "sync_flow_deleted",
        "apps/flows/src/services/flow_access_service.py",
        ("authz.delete",),
    ),
    (
        "sync_tool_saved",
        "apps/flows/src/services/flow_access_service.py",
        ("authz.write",),
    ),
    (
        "sync_tool_deleted",
        "apps/flows/src/services/flow_access_service.py",
        ("authz.delete",),
    ),
    (
        "persist_flow_with_authz",
        "apps/flows/realtime/operations.py",
        ("sync_flow_saved",),
    ),
    (
        "create_flow",
        "apps/flows/src/services/flow_factory.py",
        ("sync_flow_saved",),
    ),
    (
        "_write_binding_owner",
        "core/mail/service.py",
        ("mailbox_binding_owner_tuple",),
    ),
    (
        "_clear_binding_tuples",
        "core/mail/service.py",
        ("authz.delete",),
    ),
    (
        "patch_binding",
        "core/mail/service.py",
        ("_write_binding_owner", "_clear_binding_tuples"),
    ),
    (
        "get_or_create",
        "core/namespace/service.py",
        ("authz.write",),
    ),
    (
        "ensure_personal_namespace",
        "core/namespace/service.py",
        ("authz.write",),
    ),
    (
        "delete",
        "core/namespace/service.py",
        ("authz.delete",),
    ),
    (
        "register_device",
        "apps/agent/service.py",
        ("agent_device_owner_tuple",),
    ),
    (
        "register_device_with_auth",
        "apps/agent/service.py",
        ("agent_device_owner_tuple",),
    ),
    (
        "_persist_user",
        "core/identity/auth_service.py",
        ("sync_user_groups",),
    ),
    (
        "set_company_member_roles",
        "core/identity/company_membership.py",
        ("sync_company_member_roles",),
    ),
    (
        "create_connection",
        "core/datasources/service.py",
        ("datasource_owner_tuple", "authz.write"),
    ),
    (
        "delete_connection",
        "core/datasources/service.py",
        ("authz.delete",),
    ),
)

# Create-path files must compensate (except + rollback) when FGA write fails.
_CREATE_COMPENSATE: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "create_entity",
        "apps/crm/services/entity_service.py",
        ("except Exception", "take_by_id"),
    ),
    (
        "get_or_create_person_entity_id",
        "apps/crm/services/user_person_service.py",
        ("except Exception", "take_by_id"),
    ),
    (
        "upsert_canonical_by_external_ref",
        "apps/crm/integrations/entity_upsert.py",
        ("except Exception", "take_by_id"),
    ),
    (
        "_copy_shallow",
        "apps/crm/services/access_request_service.py",
        ("except Exception", "take_by_id"),
    ),
    (
        "_ensure_company_entity",
        "apps/crm/services/company_init_service.py",
        ("except Exception", "take_by_id"),
    ),
    (
        "persist_flow_with_authz",
        "apps/flows/realtime/operations.py",
        ("except Exception", "FlowConfig.delete_by_flow_id"),
    ),
    (
        "create_flow",
        "apps/flows/src/services/flow_factory.py",
        ("except Exception", "FlowConfig.delete_by_flow_id"),
    ),
    (
        "_load_flow_bundle",
        "apps/flows/src/services/flows_loader.py",
        ("except Exception", "FlowConfig.delete_by_flow_id"),
    ),
    (
        "register_device",
        "apps/agent/service.py",
        ("except Exception", "shared_storage.delete"),
    ),
    (
        "register_device_with_auth",
        "apps/agent/service.py",
        ("except Exception", "shared_storage.delete"),
    ),
    (
        "_persist_user",
        "core/identity/auth_service.py",
        ("except Exception",),
    ),
    (
        "_sync_created",
        "core/documents/tree_service.py",
        ("except Exception", "delete_in_namespace"),
    ),
    (
        "_bind_after_create",
        "core/files/service.py",
        ("except Exception", "delete"),
    ),
    (
        "patch_binding",
        "core/mail/service.py",
        ("except Exception",),
    ),
    (
        "add_member",
        "apps/sync/services/channel_service.py",
        ("except Exception", "delete_channel_member"),
    ),
    (
        "create_queue",
        "core/worktracker/service.py",
        ("except Exception", "delete_queue"),
    ),
    (
        "create_page",
        "apps/wiki/services/wiki_service.py",
        ("except Exception", "delete_page_in_namespace"),
    ),
    (
        "create_connection",
        "core/datasources/service.py",
        ("except Exception", "delete_by_id"),
    ),
)


def _check_symbol(
    errors: list[str],
    symbol: str,
    rel_path: str,
    required: tuple[str, ...],
) -> None:
    path = _ROOT / rel_path
    if not path.is_file():
        errors.append(f"missing dual-write target file: {rel_path} ({symbol})")
        return
    text = path.read_text(encoding="utf-8")
    if not re.search(rf"\basync def {symbol}\b|\bdef {symbol}\b", text):
        errors.append(f"expected mutator `{symbol}` in {rel_path}")
        return
    for needle in required:
        if needle not in text:
            errors.append(
                f"{rel_path}: `{symbol}` path missing dual-write marker `{needle}`"
            )


def main() -> int:
    errors: list[str] = []
    for symbol, rel_path, required in _MUTATORS:
        _check_symbol(errors, symbol, rel_path, required)
    for symbol, rel_path, required in _CREATE_COMPENSATE:
        _check_symbol(errors, symbol, rel_path, required)

    if errors:
        print("check_authz_dual_write FAILED:", file=sys.stderr)
        for item in errors:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("check_authz_dual_write OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
