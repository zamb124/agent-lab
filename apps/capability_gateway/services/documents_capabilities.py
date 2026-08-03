"""Documents SDK capabilities: definitions + DocumentsClient invoke helper."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import TypeAlias

from pydantic import BaseModel, ValidationError

from core.capabilities import CAPABILITY_LANGUAGES, CapabilityDefinition
from core.clients.documents_client import DocumentsClient
from core.clients.documents_models import (
    DocumentsAccessArgs,
    DocumentsAddCatalogMemberArgs,
    DocumentsAppendTextMutationArgs,
    DocumentsCatalogIdArgs,
    DocumentsCopyArgs,
    DocumentsCreateCatalogArgs,
    DocumentsCreateEmptyArgs,
    DocumentsEmptyArgs,
    DocumentsFileIdArgs,
    DocumentsFindArgs,
    DocumentsFromFileArgs,
    DocumentsGetLinkArgs,
    DocumentsListCatalogArgs,
    DocumentsMoveArgs,
    DocumentsPatchAccessArgs,
    DocumentsReadArgs,
    DocumentsRenameArgs,
    DocumentsReplaceTextMutationArgs,
    DocumentsUpdateCatalogArgs,
    DocumentsUpdateCellsMutationArgs,
)
from core.clients.service_client import ServiceClientError
from core.types import JsonObject, JsonValue, require_json_object

DocumentsArgsModel: TypeAlias = type[BaseModel]

_DOCUMENTS_OUTPUT_SCHEMA: JsonObject = {
    "type": "object",
    "description": "Brief JSON from DocumentsClient (product-level fields, no HTTP envelope).",
}


def _input_schema(model: DocumentsArgsModel) -> JsonObject:
    return require_json_object(model.model_json_schema(), f"{model.__name__}.json_schema")


def _definition(
    *,
    method: str,
    title: str,
    description: str,
    args_model: DocumentsArgsModel,
) -> CapabilityDefinition:
    return CapabilityDefinition(
        name=f"documents.{method}",
        title=title,
        description=description,
        input_schema=_input_schema(args_model),
        output_schema=_DOCUMENTS_OUTPUT_SCHEMA,
        languages=list(CAPABILITY_LANGUAGES),
        tags=["documents"],
        sdk_namespace="documents",
        sdk_method=method,
    )


DOCUMENTS_CAPABILITY_SPECS: tuple[tuple[str, str, str, DocumentsArgsModel], ...] = (
    (
        "from_file",
        "Bind file into Documents",
        "Creates a Documents binding for an existing platform file_id.",
        DocumentsFromFileArgs,
    ),
    (
        "replace_text",
        "Replace text in document",
        "Replaces exact text in a Documents binding (.docx/.xlsx/.txt/.csv).",
        DocumentsReplaceTextMutationArgs,
    ),
    (
        "append_text",
        "Append text to document",
        "Appends text to the end of a Documents binding.",
        DocumentsAppendTextMutationArgs,
    ),
    (
        "update_cells",
        "Update spreadsheet cells",
        "Updates Excel/CSV cells by A1-style addresses.",
        DocumentsUpdateCellsMutationArgs,
    ),
    (
        "create_empty",
        "Create empty document",
        "Creates a blank word/cell/slide document in a catalog.",
        DocumentsCreateEmptyArgs,
    ),
    (
        "rename",
        "Rename document",
        "Renames a Documents binding title by file_id.",
        DocumentsRenameArgs,
    ),
    (
        "move",
        "Move document",
        "Moves a Documents binding into another catalog.",
        DocumentsMoveArgs,
    ),
    (
        "copy",
        "Copy document",
        "Copies a Documents file into a catalog (new file_id).",
        DocumentsCopyArgs,
    ),
    (
        "delete",
        "Soft-delete document",
        "Soft-deletes a Documents binding (trash).",
        DocumentsFileIdArgs,
    ),
    (
        "list_deleted",
        "List deleted documents",
        "Lists soft-deleted Documents bindings in the active namespace.",
        DocumentsEmptyArgs,
    ),
    (
        "restore",
        "Restore document",
        "Restores a soft-deleted Documents binding from trash.",
        DocumentsFileIdArgs,
    ),
    (
        "permanent_delete",
        "Permanently delete document",
        "Permanently deletes a Documents binding that is already in trash.",
        DocumentsFileIdArgs,
    ),
    (
        "list_catalog",
        "List catalog",
        "Browses catalog tree: root catalogs or children + documents for catalog_id.",
        DocumentsListCatalogArgs,
    ),
    (
        "find",
        "Find documents",
        "Lexical/semantic/auto search in Documents catalogs.",
        DocumentsFindArgs,
    ),
    (
        "read",
        "Read document content",
        "Reads Documents file content via FileReader (page_start/page_end/budget).",
        DocumentsReadArgs,
    ),
    (
        "get_link",
        "Get document link",
        "Returns SPA editor path or preview_url for a document.",
        DocumentsGetLinkArgs,
    ),
    (
        "create_catalog",
        "Create catalog",
        "Creates a Documents catalog folder.",
        DocumentsCreateCatalogArgs,
    ),
    (
        "update_catalog",
        "Update catalog",
        "Updates catalog title and/or is_public.",
        DocumentsUpdateCatalogArgs,
    ),
    (
        "list_catalog_members",
        "List catalog members",
        "Lists explicit members of a catalog.",
        DocumentsCatalogIdArgs,
    ),
    (
        "add_catalog_member",
        "Add catalog member",
        "Adds a user_id to catalog members.",
        DocumentsAddCatalogMemberArgs,
    ),
    (
        "get_access",
        "Get access",
        "Reads unified access for a catalog or document.",
        DocumentsAccessArgs,
    ),
    (
        "patch_access",
        "Patch access",
        "Patches catalog/document access fields.",
        DocumentsPatchAccessArgs,
    ),
    (
        "rotate_public_link",
        "Rotate public link",
        "Rotates the public link token and returns public_url.",
        DocumentsAccessArgs,
    ),
    (
        "catalog_rag_status",
        "Catalog RAG status",
        "Returns catalog RAG index status.",
        DocumentsCatalogIdArgs,
    ),
    (
        "catalog_rag_enable",
        "Enable catalog RAG",
        "Enables semantic RAG index for a catalog.",
        DocumentsCatalogIdArgs,
    ),
    (
        "catalog_rag_disable",
        "Disable catalog RAG",
        "Disables catalog RAG index.",
        DocumentsCatalogIdArgs,
    ),
    (
        "catalog_rag_rebuild",
        "Rebuild catalog RAG",
        "Rebuilds the catalog RAG index.",
        DocumentsCatalogIdArgs,
    ),
)


def documents_capability_definitions() -> dict[str, CapabilityDefinition]:
    return {
        f"documents.{method}": _definition(
            method=method,
            title=title,
            description=description,
            args_model=args_model,
        )
        for method, title, description, args_model in DOCUMENTS_CAPABILITY_SPECS
    }


def documents_args_model_for(method: str) -> DocumentsArgsModel:
    for spec_method, _title, _description, args_model in DOCUMENTS_CAPABILITY_SPECS:
        if spec_method == method:
            return args_model
    raise ValueError(f"Unknown documents capability method: {method}")


def _documents_method_call(method: str, args: BaseModel) -> Awaitable[JsonObject]:
    client = DocumentsClient()
    if isinstance(args, DocumentsEmptyArgs):
        if method == "list_deleted":
            return client.list_deleted()
        raise ValueError(f"Unsupported documents empty-args method: {method}")
    if method == "from_file" and isinstance(args, DocumentsFromFileArgs):
        return client.from_file(args)
    if method == "replace_text" and isinstance(args, DocumentsReplaceTextMutationArgs):
        return client.replace_text(args)
    if method == "append_text" and isinstance(args, DocumentsAppendTextMutationArgs):
        return client.append_text(args)
    if method == "update_cells" and isinstance(args, DocumentsUpdateCellsMutationArgs):
        return client.update_cells(args)
    if method == "create_empty" and isinstance(args, DocumentsCreateEmptyArgs):
        return client.create_empty(args)
    if method == "rename" and isinstance(args, DocumentsRenameArgs):
        return client.rename(args)
    if method == "move" and isinstance(args, DocumentsMoveArgs):
        return client.move(args)
    if method == "copy" and isinstance(args, DocumentsCopyArgs):
        return client.copy(args)
    if method == "delete" and isinstance(args, DocumentsFileIdArgs):
        return client.delete(args)
    if method == "restore" and isinstance(args, DocumentsFileIdArgs):
        return client.restore(args)
    if method == "permanent_delete" and isinstance(args, DocumentsFileIdArgs):
        return client.permanent_delete(args)
    if method == "list_catalog" and isinstance(args, DocumentsListCatalogArgs):
        return client.list_catalog(args)
    if method == "find" and isinstance(args, DocumentsFindArgs):
        return client.find(args)
    if method == "read" and isinstance(args, DocumentsReadArgs):
        return client.read(args)
    if method == "get_link" and isinstance(args, DocumentsGetLinkArgs):
        return client.get_link(args)
    if method == "create_catalog" and isinstance(args, DocumentsCreateCatalogArgs):
        return client.create_catalog(args)
    if method == "update_catalog" and isinstance(args, DocumentsUpdateCatalogArgs):
        return client.update_catalog(args)
    if method == "list_catalog_members" and isinstance(args, DocumentsCatalogIdArgs):
        return client.list_catalog_members(args)
    if method == "add_catalog_member" and isinstance(args, DocumentsAddCatalogMemberArgs):
        return client.add_catalog_member(args)
    if method == "get_access" and isinstance(args, DocumentsAccessArgs):
        return client.get_access(args)
    if method == "patch_access" and isinstance(args, DocumentsPatchAccessArgs):
        return client.patch_access(args)
    if method == "rotate_public_link" and isinstance(args, DocumentsAccessArgs):
        return client.rotate_public_link(args)
    if method == "catalog_rag_status" and isinstance(args, DocumentsCatalogIdArgs):
        return client.catalog_rag_status(args)
    if method == "catalog_rag_enable" and isinstance(args, DocumentsCatalogIdArgs):
        return client.catalog_rag_enable(args)
    if method == "catalog_rag_disable" and isinstance(args, DocumentsCatalogIdArgs):
        return client.catalog_rag_disable(args)
    if method == "catalog_rag_rebuild" and isinstance(args, DocumentsCatalogIdArgs):
        return client.catalog_rag_rebuild(args)
    raise ValueError(f"Unsupported documents capability invoke: {method}")


async def invoke_documents_client(method: str, kwargs: JsonObject) -> JsonValue:
    """Parse kwargs with the method's model and call DocumentsClient (Context must be active)."""
    args_model = documents_args_model_for(method)
    try:
        args = args_model.model_validate(kwargs)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
    try:
        return await _documents_method_call(method, args)
    except ServiceClientError as exc:
        raise ValueError(str(exc)) from exc
