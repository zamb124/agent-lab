#!/usr/bin/env python3
"""CI gate: unified Files API — zero legacy symbols in apps/ and tests/."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

LEGACY_SYMBOLS: tuple[tuple[str, str], ...] = (
    (r"\bFileProcessor\b", "FileProcessor"),
    (r"\bget_default_file_processor\b", "get_default_file_processor"),
    (r"\bbuild_file_api_router\b", "build_file_api_router"),
    (r"\bpersist_uploaded\b", "persist_uploaded"),
    (r"\bupload_namespace_document\b", "upload_namespace_document"),
    (r"\.file_processor\b", "file_processor"),
)

FORBIDDEN_FACTORY_NAMES: tuple[str, ...] = (
    "sync/file_upload",
    "flows/file_upload",
    "crm/file_upload",
    "worktracker/file_upload",
    "rag/file_upload",
)

# Single-shot FormData POST на корень Files API (не /uploads, не /download, не domain routes).
SINGLE_SHOT_FILES_POST = re.compile(
    r"""(?:\.post\(\s*['\"]/(?:frontend|flows|crm|sync|rag|worktracker|documents)/api/v1/files/['\"]"""
    r"""|path:\s*['\"]/(?:frontend|flows|crm|sync|rag|worktracker|documents)/api/v1/files/['\"])"""
)

SCAN_DIRS = (
    REPO_ROOT / "apps",
    REPO_ROOT / "tests",
)

ALLOWLIST_PATHS: tuple[Path, ...] = (
    REPO_ROOT / "apps" / "crm_worker" / "worker.py",
    REPO_ROOT / "apps" / "crm" / "README.md",
)


def _is_allowlisted(path: Path) -> bool:
    for allowed in ALLOWLIST_PATHS:
        if path.resolve() == allowed.resolve():
            return True
    return False


def _scan_for_legacy() -> list[str]:
    errors: list[str] = []
    for base in SCAN_DIRS:
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in {".py", ".js", ".md", ".mdc"}:
                continue
            if _is_allowlisted(path):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            rel = path.relative_to(REPO_ROOT)
            for pattern, label in LEGACY_SYMBOLS:
                if re.search(pattern, text):
                    errors.append(f"{rel}: forbidden legacy symbol {label}")
            if path.suffix == ".js":
                for factory_name in FORBIDDEN_FACTORY_NAMES:
                    if f"name: '{factory_name}'" in text or f'name: "{factory_name}"' in text:
                        errors.append(f"{rel}: forbidden factory {factory_name}")
            # Single-shot gate only for production code; tests may assert rejection.
            if base.name == "apps" and SINGLE_SHOT_FILES_POST.search(text):
                errors.append(f"{rel}: single-shot POST /api/v1/files/ forbidden (use /uploads)")
    return errors


def _check_files_router_mount() -> list[str]:
    errors: list[str] = []
    factory_path = REPO_ROOT / "core" / "app" / "factory.py"
    text = factory_path.read_text(encoding="utf-8")
    if "build_file_api_router" in text:
        errors.append("core/app/factory.py: build_file_api_router must not be mounted")
    if "build_files_router" not in text:
        errors.append("core/app/factory.py: build_files_router must be mounted")
    if "files_api_prefix" not in text:
        errors.append("core/app/factory.py: files_api_prefix must mount Files API on each service")
    return errors


def _check_docs_placement_coverage() -> list[str]:
    """Every FileSourceKind must be auto-placement or explicit exempt."""
    from core.files.create_spec import FileSourceKind
    from core.files.registry import (
        DOCS_PLACEMENT_EXEMPT_SOURCE_KINDS,
        SOURCE_KIND_TO_DOCS_PLACEMENT,
    )

    errors: list[str] = []
    for kind in FileSourceKind:
        if kind in DOCS_PLACEMENT_EXEMPT_SOURCE_KINDS:
            if kind in SOURCE_KIND_TO_DOCS_PLACEMENT:
                errors.append(
                    f"FileSourceKind.{kind.name} is both exempt and mapped for DocsPlacement"
                )
            continue
        if kind not in SOURCE_KIND_TO_DOCS_PLACEMENT:
            errors.append(
                f"FileSourceKind.{kind.name} missing from docs auto-placement mapping "
                f"(add to SOURCE_KIND_TO_DOCS_PLACEMENT or DOCS_PLACEMENT_EXEMPT_SOURCE_KINDS)"
            )
    return errors


FLOW_UI_HOST = (
    REPO_ROOT
    / "core"
    / "frontend"
    / "static"
    / "lib"
    / "flow-ui"
    / "components"
    / "platform-flow-ui.js"
)


def _check_flow_ui_no_base64_upload() -> list[str]:
    """platform-flow-ui must upload files via resolvePlatformFileRefs, not base64."""
    errors: list[str] = []
    text = FLOW_UI_HOST.read_text(encoding="utf-8")
    if "_fileToBase64Part" in text:
        errors.append("platform-flow-ui.js: _fileToBase64Part must be removed")
    if "readAsDataURL" in text:
        errors.append("platform-flow-ui.js: readAsDataURL file upload path forbidden")
    if "resolvePlatformFileRefs" not in text:
        errors.append("platform-flow-ui.js: must use resolvePlatformFileRefs for outbound files")
    return errors


def _check_a2a_stream_url_only() -> list[str]:
    """Platform A2A builder accepts only url/file_id file parts."""
    errors: list[str] = []
    path = (
        REPO_ROOT
        / "core"
        / "frontend"
        / "static"
        / "lib"
        / "flow-ui"
        / "protocol"
        / "a2a-codec.js"
    )
    text = path.read_text(encoding="utf-8")
    if "typeof f.raw === 'string'" in text:
        errors.append("a2a-codec.js: buildA2aFileParts must not accept f.raw")
    if "fw.bytes" in text:
        errors.append("a2a-codec.js: buildA2aFileParts must not accept file.bytes")
    if "f.data != null" in text or "f && f.data" in text:
        errors.append("a2a-codec.js: buildA2aFileParts must not accept f.data fallback")
    if "file part requires url" not in text:
        errors.append("a2a-codec.js: buildA2aFileParts must require url for file parts")
    return errors


def _check_mail_no_content_base64() -> list[str]:
    """Mail public attachment and modal: file_id only, no content_base64."""
    errors: list[str] = []
    models = REPO_ROOT / "core" / "mail" / "models.py"
    models_text = models.read_text(encoding="utf-8")
    if "content_base64" in models_text:
        errors.append("core/mail/models.py: content_base64 must be removed")
    if "attachment.file_id required" not in models_text:
        errors.append("core/mail/models.py: MailSendPayload must require attachment.file_id")
    modal = (
        REPO_ROOT
        / "core"
        / "frontend"
        / "static"
        / "lib"
        / "components"
        / "platform-mail-modal.js"
    )
    modal_text = modal.read_text(encoding="utf-8")
    if "content_base64" in modal_text:
        errors.append("platform-mail-modal.js: content_base64 download path forbidden")
    if "atob(" in modal_text:
        errors.append("platform-mail-modal.js: atob attachment download forbidden")
    service = REPO_ROOT / "core" / "mail" / "service.py"
    service_text = service.read_text(encoding="utf-8")
    if "to_public_inbound" in service_text:
        errors.append("core/mail/service.py: to_public_inbound must be removed")
    if "include_attachment_content" in service_text:
        errors.append("core/mail/service.py: include_attachment_content must be removed")
    return errors


def _check_public_search_no_base64_upload() -> list[str]:
    """Public search: browser files → chunked upload + Part.url, not base64."""
    errors: list[str] = []
    path = (
        REPO_ROOT
        / "apps"
        / "frontend"
        / "ui"
        / "_helpers"
        / "public-search-files.js"
    )
    text = path.read_text(encoding="utf-8")
    if "readAsDataURL" in text:
        errors.append("public-search-files.js: readAsDataURL forbidden")
    if "fileToPublicSearchA2aPart" in text or "filesToPublicSearchA2aParts" in text:
        errors.append("public-search-files.js: base64 A2A part helpers must be removed")
    if "uploadPlatformFile" not in text:
        errors.append("public-search-files.js: must use uploadPlatformFile")
    if "uploadPublicSearchFilesForA2a" not in text:
        errors.append("public-search-files.js: uploadPublicSearchFilesForA2a required")
    resource = (
        REPO_ROOT
        / "apps"
        / "frontend"
        / "ui"
        / "events"
        / "resources"
        / "public-search.resource.js"
    )
    resource_text = resource.read_text(encoding="utf-8")
    if "uploadPublicSearchFilesForA2a" not in resource_text:
        errors.append("public-search.resource.js: must call uploadPublicSearchFilesForA2a")
    if "item.data" in resource_text and "files[" in resource_text:
        errors.append("public-search.resource.js: base64 files[n].data payload forbidden")
    return errors


def _check_markdown_editor_no_base64_attach() -> list[str]:
    """Mail compose attachments: chunked upload + file_id, not btoa(arrayBuffer)."""
    errors: list[str] = []
    path = (
        REPO_ROOT
        / "core"
        / "frontend"
        / "static"
        / "lib"
        / "components"
        / "platform-markdown-editor.js"
    )
    text = path.read_text(encoding="utf-8")
    if "content_base64" in text:
        errors.append("platform-markdown-editor.js: content_base64 attach forbidden")
    if "btoa(" in text:
        errors.append("platform-markdown-editor.js: btoa file attach forbidden")
    if "arrayBuffer()" in text:
        errors.append("platform-markdown-editor.js: arrayBuffer file attach forbidden")
    if "uploadPlatformFile" not in text:
        errors.append("platform-markdown-editor.js: must use uploadPlatformFile")
    reducer = (
        REPO_ROOT
        / "core"
        / "frontend"
        / "static"
        / "lib"
        / "events"
        / "reducers"
        / "mail.js"
    )
    reducer_text = reducer.read_text(encoding="utf-8")
    if "content_base64 required" in reducer_text:
        errors.append("mail.js reducer: content_base64 compose path must be removed")
    if "attachment.file_id required" not in reducer_text:
        errors.append("mail.js reducer: attachment.file_id required")
    return errors


def _check_chunked_only_upload() -> list[str]:
    """No single-shot FormData POST /files/ and no single_shot_max_bytes."""
    errors: list[str] = []
    api_path = REPO_ROOT / "core" / "files" / "api.py"
    api_text = api_path.read_text(encoding="utf-8")
    if 'router.add_api_route("/",' in api_text or 'add_api_route("/", upload' in api_text:
        errors.append("core/files/api.py: POST / single-shot upload must be removed")
    if "UploadFile" in api_text or "single_shot" in api_text:
        errors.append("core/files/api.py: UploadFile/single_shot must be removed")

    config_path = REPO_ROOT / "core" / "config" / "models.py"
    if "single_shot_max_bytes" in config_path.read_text(encoding="utf-8"):
        errors.append("core/config/models.py: single_shot_max_bytes must be removed")

    files_url_js = (
        REPO_ROOT
        / "core"
        / "frontend"
        / "static"
        / "lib"
        / "utils"
        / "platform-files-url.js"
    )
    if not files_url_js.is_file():
        errors.append("platform-files-url.js must exist")
    else:
        files_url_text = files_url_js.read_text(encoding="utf-8")
        if "resolvePlatformFilesApiBase" not in files_url_text:
            errors.append("platform-files-url.js: resolvePlatformFilesApiBase required")
        if "setPlatformFilesRouteSegment" not in files_url_text:
            errors.append("platform-files-url.js: setPlatformFilesRouteSegment required")

    app_js = (
        REPO_ROOT
        / "core"
        / "frontend"
        / "static"
        / "lib"
        / "base"
        / "PlatformApp.js"
    )
    if "setPlatformFilesRouteSegment" not in app_js.read_text(encoding="utf-8"):
        errors.append("PlatformApp.js: must bind files route segment via setPlatformFilesRouteSegment")

    upload_js = (
        REPO_ROOT
        / "core"
        / "frontend"
        / "static"
        / "lib"
        / "utils"
        / "platform-file-upload.js"
    )
    upload_text = upload_js.read_text(encoding="utf-8")
    if "_uploadSingleShot" in upload_text or "singleShotMaxBytes" in upload_text:
        errors.append("platform-file-upload.js: single-shot branch must be removed")
    if "FormData" in upload_text:
        errors.append("platform-file-upload.js: FormData upload forbidden")
    if "const FILES_BASE = '/frontend/api/v1/files'" in upload_text:
        errors.append("platform-file-upload.js: hardcoded frontend FILES_BASE forbidden")
    if "resolvePlatformFilesApiBase" not in upload_text:
        errors.append("platform-file-upload.js: must use resolvePlatformFilesApiBase")

    multipart_path = (
        REPO_ROOT
        / "core"
        / "frontend"
        / "static"
        / "lib"
        / "events"
        / "factories"
        / "_multipart-upload.js"
    )
    if multipart_path.is_file():
        errors.append("_multipart-upload.js must be deleted")

    events_index = (
        REPO_ROOT / "core" / "frontend" / "static" / "lib" / "events" / "index.js"
    )
    if "createMultipartFileUploadOp" in events_index.read_text(encoding="utf-8"):
        errors.append("events/index.js: createMultipartFileUploadOp export must be removed")

    forbidden_formdata_posts = (
        (
            REPO_ROOT
            / "core"
            / "frontend"
            / "static"
            / "lib"
            / "events"
            / "resources"
            / "rag-documents.resource.js",
            "/frontend/api/v1/files/",
        ),
        (
            REPO_ROOT
            / "apps"
            / "office"
            / "ui"
            / "events"
            / "resources"
            / "documents.resource.js",
            "FormData",
        ),
        (
            REPO_ROOT
            / "apps"
            / "crm"
            / "ui"
            / "events"
            / "resources"
            / "attachments.resource.js",
            "FormData",
        ),
        (
            REPO_ROOT
            / "core"
            / "frontend"
            / "static"
            / "lib"
            / "events"
            / "effects"
            / "files.effect.js",
            "FormData",
        ),
    )
    for path, needle in forbidden_formdata_posts:
        text = path.read_text(encoding="utf-8")
        if needle in text:
            errors.append(f"{path.relative_to(REPO_ROOT)}: forbidden `{needle}` in upload path")
    return errors


def main() -> int:
    errors = _scan_for_legacy()
    errors.extend(_check_files_router_mount())
    errors.extend(_check_docs_placement_coverage())
    errors.extend(_check_flow_ui_no_base64_upload())
    errors.extend(_check_a2a_stream_url_only())
    errors.extend(_check_mail_no_content_base64())
    errors.extend(_check_public_search_no_base64_upload())
    errors.extend(_check_markdown_editor_no_base64_attach())
    errors.extend(_check_chunked_only_upload())
    if errors:
        print("check_files_canon: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print("check_files_canon: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
