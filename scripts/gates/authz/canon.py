#!/usr/bin/env python3
"""CI gate: OpenFGA AuthzService is sole PDP; no legacy hats / roster-admin Check / soft-fail."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from scripts.gates.kit import REPO_ROOT as _ROOT

_OPENFGA_IMPORT = re.compile(r"^\s*(from|import)\s+openfga_sdk\b", re.M)
_FORBIDDEN_CORE_CRM = _ROOT / "core" / "authz" / "crm_tuples.py"
_FORBIDDEN_LEGACY_PERMISSIONS = _ROOT / "core" / "auth" / "permissions.py"
_PERMISSIONS_ENABLED = re.compile(r"\bpermissions_enabled\b")
_PERMISSION_CHECKER = re.compile(r"\b(?:Tool)?PermissionChecker\b")
_TOOL_PERMISSION_BIND = re.compile(
    r"\b(?:bind|reset)_tool_permission_checker\b"
)
_ACCESS_CONTROL_SERVICE = re.compile(r"\bAccessControlService\b")
_CAN_READ_ENTITY = re.compile(r"\bcan_read_entity\b")
_WIKI_ACCESS_RESOLVER = re.compile(r"\bWikiAccessResolver\b")
_DOCUMENT_SHARE_REPO = re.compile(r"\bDocumentShareRepository\b")
_ENABLED_OBJECT_TYPES = re.compile(
    r"\benabled_object_types\b|OPENFGA__ENABLED_OBJECT_TYPES"
)
_COMPANY_ADMIN_ROLES = re.compile(r"\b_COMPANY_ADMIN_ROLES\b")
_ADMIN_ROLES_CONST = re.compile(r"\b_ADMIN_ROLES\b")
_ROSTER_ADMIN_CHECK = re.compile(
    r"""["']admin["']\s+not\s+in\s+\w*(?:roles|user_roles)\b"""
    r"""|\b\w*(?:roles|user_roles)\b.*["']admin["']\s+not\s+in""",
    re.M,
)
_AUTHZ_DENIED_PASS = re.compile(
    r"except\s+AuthzDenied\s*:\s*(?:pass\b|\.\.\.)",
    re.M,
)
_WIRE_INTERACT = re.compile(
    r"""(?:permission|link_permission)\s*[:=]\s*['"]interact['"]"""
    r"""|['"]interact['"]\s*(?:as\s+)?(?:permission|link_permission)"""
)
_WIRE_COMMENT_ACL = re.compile(
    r"""(?:permission|link_permission)\s*[:=]\s*['"]comment['"]"""
)
_WIRE_VIEW_EDIT_PERM = re.compile(
    r"""(?:permission|link_permission)\s*[:=]\s*['"](?:view|edit)['"]"""
)
_GROUP_FACTORY = re.compile(
    r"(?:AuthzObject\.group|AuthzSubject\.group_member|group_member_tuple)\("
)
_BAD_AUTHZ_RELATION = re.compile(
    r"\bAuthzRelation\.(?!"
    r"OWNER|ADMIN|EDITOR|VIEWER|MEMBER|MANAGER|PARENT|COMPANY|PLATFORM|"
    r"NAMESPACE|CATALOG|SOURCE|LISTER|FLOW|COMPANY_VIEWER|CAN_SHARE|CAN_VIEW|CAN_EDIT|CAN_ADMIN|CAN_LIST"
    r")\w+\b"
)
_UI_JWT_ADMIN_GATE = re.compile(
    r"""(?:companies\[[^\]]+\]|\.companies\[[^\]]+\])\.includes\(\s*['"]admin['"]\s*\)"""
    r"""|raw\.companies\[[^\]]*\][^\n]{0,80}includes\(\s*['"]admin['"]\s*\)"""
    r"""|raw\.roles\.includes\(\s*['"](?:admin|owner)['"]\s*\)"""
)
_TEST_MEMBERS_ASSIGN = re.compile(
    r"""company\.members\[[^\]]+\]\s*="""
    r"""|company\.members\s*="""
    r"""|Company\s*\([^)]{0,400}members\s*="""
)
_TEST_SYNC_MARKERS = (
    "sync_company_member_roles",
    "set_test_company_member_roles",
    "set_company_member_roles",
    "remove_company_member",
    "remove_company_membership",
)

# Roster dual-write / JWT issue — не PDP Check.
_ROSTER_ALLOWLIST = frozenset(
    {
        Path("core/identity/company_membership.py"),
        Path("core/authz/company_sync.py"),
        Path("core/utils/tokens.py"),
        Path("core/utils/auth_session_rebind.py"),
        Path("core/identity/auth_service.py"),
        Path("scripts/gates/authz/canon.py"),
    }
)

_TEST_MEMBERS_ALLOWLIST = frozenset(
    {
        Path("tests/fixtures/auth.py"),
        Path("scripts/gates/authz/canon.py"),
        Path("tests/core/db/test_company_repository_members.py"),
    }
)

# UI may display roster roles; admin mutate gate must be server-driven can_admin.
_UI_ADMIN_GATE_ALLOWLIST = frozenset(
    {
        Path("scripts/gates/authz/canon.py"),
    }
)

# OnlyOffice Document Server wire keys (не platform ACL axis).
_WIRE_VIEW_EDIT_ALLOWLIST = frozenset(
    {
        Path("apps/office/services/viewer_handlers/onlyoffice_handler.py"),
        Path("scripts/gates/authz/canon.py"),
    }
)


def _balanced_call(text: str, start: int) -> str:
    depth = 0
    index = start
    while index < len(text):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
        index += 1
    return text[start : start + 200]


def _group_factory_call_ok(snippet: str) -> bool:
    if "company_id" in snippet:
        return True
    if "PLATFORM_ADMIN_GROUP" in snippet:
        return True
    if re.search(r"""['"]admin['"]""", snippet):
        return True
    return False


def _iter_py_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*.py"):
        if any(part in {"__pycache__", ".venv", "node_modules"} for part in path.parts):
            continue
        files.append(path)
    return files


def _iter_js_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in (p for g in ("*.js", "*.ts") for p in root.rglob(g)):
        if any(part in {"__pycache__", ".venv", "node_modules", "dist"} for part in path.parts):
            continue
        files.append(path)
    return files


def main() -> int:
    errors: list[str] = []
    if _FORBIDDEN_CORE_CRM.is_file():
        errors.append(
            "core/authz/crm_tuples.py forbidden — CRM helpers live in apps/crm/authz/"
        )
    if _FORBIDDEN_LEGACY_PERMISSIONS.is_file():
        errors.append(
            "core/auth/permissions.py forbidden — OpenFGA AuthzService is sole PDP"
        )

    scan_roots = (_ROOT / "apps", _ROOT / "core", _ROOT / "tests", _ROOT / "scripts")
    for root in scan_roots:
        if not root.is_dir():
            continue
        for path in _iter_py_files(root):
            text = path.read_text(encoding="utf-8")
            rel = path.relative_to(_ROOT)
            if rel.as_posix() == "scripts/gates/authz/canon.py":
                continue
            if path.is_relative_to(_ROOT / "apps") or (
                path.is_relative_to(_ROOT / "core")
                and not path.is_relative_to(_ROOT / "core" / "authz")
            ):
                if _OPENFGA_IMPORT.search(text):
                    errors.append(f"openfga_sdk import outside core/authz: {rel}")
            if _PERMISSIONS_ENABLED.search(text):
                errors.append(f"legacy permissions_enabled flag: {rel}")
            if _PERMISSION_CHECKER.search(text):
                errors.append(f"legacy PermissionChecker reference: {rel}")
            if _TOOL_PERMISSION_BIND.search(text):
                errors.append(f"legacy tool permission checker bind: {rel}")
            if _ACCESS_CONTROL_SERVICE.search(text):
                errors.append(f"legacy AccessControlService reference: {rel}")
            if _CAN_READ_ENTITY.search(text):
                errors.append(f"legacy can_read_entity reference: {rel}")
            if _WIKI_ACCESS_RESOLVER.search(text):
                errors.append(f"legacy WikiAccessResolver reference: {rel}")
            if _DOCUMENT_SHARE_REPO.search(text):
                errors.append(f"legacy DocumentShareRepository reference: {rel}")
            if _ENABLED_OBJECT_TYPES.search(text):
                errors.append(f"cutover hatch enabled_object_types: {rel}")
            if _AUTHZ_DENIED_PASS.search(text):
                errors.append(f"except AuthzDenied: pass (soft-fail forbidden): {rel}")
            if _COMPANY_ADMIN_ROLES.search(text):
                errors.append(f"roster PDP constant _COMPANY_ADMIN_ROLES: {rel}")
            if _ADMIN_ROLES_CONST.search(text) and rel not in _ROSTER_ALLOWLIST:
                if path.is_relative_to(_ROOT / "apps") or path.is_relative_to(
                    _ROOT / "core"
                ):
                    errors.append(f"roster PDP constant _ADMIN_ROLES: {rel}")
            if (
                _ROSTER_ADMIN_CHECK.search(text)
                and rel not in _ROSTER_ALLOWLIST
                and (
                    path.is_relative_to(_ROOT / "apps")
                    or path.is_relative_to(_ROOT / "core")
                )
            ):
                errors.append(f"roster-admin Check (use AuthzService): {rel}")
            if _BAD_AUTHZ_RELATION.search(text):
                errors.append(f"non-canonical AuthzRelation: {rel}")
            if (
                path.is_relative_to(_ROOT / "apps")
                or path.is_relative_to(_ROOT / "core")
                or path.is_relative_to(_ROOT / "tests")
            ):
                for match in _GROUP_FACTORY.finditer(text):
                    snippet = _balanced_call(text, match.start())
                    if not _group_factory_call_ok(snippet):
                        errors.append(
                            "tenant group must be group:{company}/{name} "
                            f"(admin is the only global group): {rel}"
                        )
                        break
            if _WIRE_INTERACT.search(text):
                errors.append(f"wire ACL permission 'interact' forbidden: {rel}")
            if _WIRE_COMMENT_ACL.search(text) and rel not in _WIRE_VIEW_EDIT_ALLOWLIST:
                errors.append(f"wire ACL permission 'comment' forbidden: {rel}")
            if _WIRE_VIEW_EDIT_PERM.search(text) and rel not in _WIRE_VIEW_EDIT_ALLOWLIST:
                errors.append(
                    f"wire ACL permission view|edit forbidden (use viewer|editor): {rel}"
                )
            if (
                path.is_relative_to(_ROOT / "tests")
                and rel not in _TEST_MEMBERS_ALLOWLIST
                and _TEST_MEMBERS_ASSIGN.search(text)
                and not any(marker in text for marker in _TEST_SYNC_MARKERS)
            ):
                errors.append(
                    f"test membership mutate without sync_company_member_roles: {rel}"
                )

        for path in _iter_js_files(root):
            text = path.read_text(encoding="utf-8")
            rel = path.relative_to(_ROOT)
            if _WIRE_INTERACT.search(text):
                errors.append(f"wire ACL permission 'interact' forbidden: {rel}")
            if re.search(
                r"""permission\s*:\s*['"](?:view|edit|comment)['"]""",
                text,
            ):
                errors.append(
                    f"wire ACL permission view|edit|comment forbidden (use viewer|editor): {rel}"
                )
            if (
                (
                    path.is_relative_to(_ROOT / "apps")
                    and "ui" in path.parts
                )
                or path.is_relative_to(_ROOT / "core" / "frontend")
            ) and _UI_JWT_ADMIN_GATE.search(text) and rel not in _UI_ADMIN_GATE_ALLOWLIST:
                errors.append(
                    f"UI JWT roster admin gate forbidden (use server can_admin): {rel}"
                )

    env_files = list((_ROOT / "reports").glob("openfga*.env*")) if (
        _ROOT / "reports"
    ).is_dir() else []
    for env_path in env_files:
        env_text = env_path.read_text(encoding="utf-8")
        if "OPENFGA__ENABLED_OBJECT_TYPES" in env_text:
            errors.append(
                f"OPENFGA__ENABLED_OBJECT_TYPES in env file: {env_path.relative_to(_ROOT)}"
            )

    channel_repo = _ROOT / "apps/sync/db/repositories/channel_repository.py"
    if channel_repo.is_file():
        ch_text = channel_repo.read_text(encoding="utf-8")
        if re.search(r"async def list_member_user_ids\b", ch_text):
            errors.append(
                "ChannelRepository.list_member_user_ids is SQL ACL; "
                "use SyncChannelAccessService / list_settings_user_ids"
            )

    channel_service = _ROOT / "apps/sync/services/channel_service.py"
    ops = _ROOT / "apps/sync/realtime/operations.py"
    if channel_service.is_file() and ops.is_file():
        service_text = channel_service.read_text(encoding="utf-8")
        ops_text = ops.read_text(encoding="utf-8")
        if "async def filter_visible" not in service_text or "batch_check" not in service_text:
            errors.append(
                "SyncChannelService.filter_visible must intersect SQL candidates with FGA can_view"
            )
        if "await self.filter_visible(" not in service_text:
            errors.append("SyncChannelService.list_channels must call filter_visible")
        if "channel_service.list_channels" not in ops_text:
            errors.append("op_channels_list must list via SyncChannelService.list_channels")
        if "channel_service.list_shared_channels" not in ops_text:
            errors.append(
                "op_company_shared_channels_list must list via SyncChannelService.list_shared_channels"
            )
        shared_match = re.search(
            r"async def list_shared_channels\(.*?(?=\n    async def |\Z)",
            service_text,
            re.DOTALL,
        )
        if shared_match is None or "await self.filter_visible(" not in shared_match.group(0):
            errors.append(
                "SyncChannelService.list_shared_channels must call filter_visible"
            )

    access_check_def = re.compile(
        r"async def (require_can_|user_can_view|user_can_admin)\b"
    )
    office_extra_allow = frozenset(
        {"user_can_view_document", "user_can_manage_trashed_binding"}
    )
    for path in _iter_py_files(_ROOT / "apps"):
        rel = path.relative_to(_ROOT)
        name = path.name
        if name.endswith("access_service.py") or path.parent.name == "authz":
            text = path.read_text(encoding="utf-8")
            for match in access_check_def.finditer(text):
                method = match.group(0).split()[-1]
                if method in office_extra_allow:
                    continue
                errors.append(
                    f"AccessService Check façade forbidden (use AuthzService): {rel} {method}"
                )

    access_call = re.compile(
        r"(?:_access_service|channel_access_service)\.(?:require_can_|user_can_view\()"
    )
    http_scan = list((_ROOT / "apps").glob("*/api/**/*.py"))
    http_scan.extend((_ROOT / "apps").glob("*/src/api/**/*.py"))
    http_scan.append(_ROOT / "apps/sync/realtime/operations.py")
    http_scan.append(_ROOT / "apps/sync/realtime/handlers.py")
    http_scan.append(_ROOT / "apps/sync/realtime/call_handlers.py")
    http_scan.append(_ROOT / "apps/flows/src/channels/base.py")
    http_scan.append(_ROOT / "apps/flows/src/services/flow_ui_share_service.py")
    for path in http_scan:
        if not path.is_file():
            continue
        rel = path.relative_to(_ROOT)
        text = path.read_text(encoding="utf-8")
        if access_call.search(text):
            errors.append(
                f"HTTP/ops Check via AccessService forbidden (use AuthzService): {rel}"
            )

    authz_init = (_ROOT / "core/authz/__init__.py").read_text(encoding="utf-8")
    if "require_authz" in authz_init or "fastapi_deps" in authz_init:
        errors.append("require_authz must not be re-exported from core.authz")
    if (_ROOT / "core/authz/fastapi_deps.py").is_file():
        errors.append("core/authz/fastapi_deps.py forbidden — HTTP Check is AuthzService")

    if errors:
        print("check_authz_canon FAILED:", file=sys.stderr)
        for item in errors:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("check_authz_canon OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
