"""HTTP client for Office Documents API on top of ServiceClient."""

from __future__ import annotations

from typing import Literal
from urllib.parse import quote

from core.clients.documents_models import (
    DocumentsAccessArgs,
    DocumentsAccessMemberItem,
    DocumentsAddCatalogMemberArgs,
    DocumentsAppendTextMutationArgs,
    DocumentsCatalogIdArgs,
    DocumentsCopyArgs,
    DocumentsCreateCatalogArgs,
    DocumentsCreateEmptyArgs,
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
from core.clients.files_client import FilesClient
from core.clients.service_client import NAMESPACE_HEADER, ServiceClient
from core.context import resolve_namespace_or_raise
from core.documents.placement import DocsBindResult, DocsPlacement
from core.files.file_ref import FileRef
from core.files.reader.engine import read_files_to_envelope
from core.files.reader.models import CompressionMode, ReadFileArgs
from core.types import JsonObject, JsonValue, require_json_array, require_json_object

_API = "/documents/api/v1"
AccessResourceKind = Literal["catalog", "document"]
FindMode = Literal["auto", "semantic", "lexical"]
LinkKind = Literal["editor", "preview"]
DocumentType = Literal["word", "cell", "slide"]
SpreadsheetFormat = Literal["xlsx", "csv"]
CellValue = str | int | float | bool | None


class DocumentsClient:
    """REST client for office documents; namespace from context via X-Platform-Namespace."""

    def __init__(self, service_client: ServiceClient | None = None) -> None:
        self._http: ServiceClient = (
            service_client if service_client is not None else ServiceClient()
        )

    def _ns_headers(self) -> dict[str, str]:
        return {NAMESPACE_HEADER: resolve_namespace_or_raise()}

    @staticmethod
    def _as_objects(value: object, label: str) -> list[JsonObject]:
        items = require_json_array(value, label)
        return [require_json_object(item, f"{label}[{index}]") for index, item in enumerate(items)]

    @staticmethod
    def _document_item_brief(raw: JsonObject) -> JsonObject:
        return {
            "file_id": raw.get("file_id"),
            "catalog_id": raw.get("catalog_id"),
            "title": raw.get("title"),
            "file_category": raw.get("file_category"),
            "onlyoffice_document_type": raw.get("onlyoffice_document_type"),
            "updated_at": raw.get("updated_at"),
            "file_size": raw.get("file_size"),
        }

    @staticmethod
    def _catalog_summary(item: JsonObject) -> JsonObject:
        return {
            "catalog_id": item["catalog_id"],
            "title": item["title"],
            "file_count": item.get("file_count"),
            "rag_index_enabled": item.get("rag_index_enabled"),
            "parent_catalog_id": item.get("parent_catalog_id"),
        }

    @staticmethod
    def _document_summary(item: JsonObject) -> JsonObject:
        return {
            "file_id": item["file_id"],
            "title": item["title"],
            "file_category": item.get("file_category"),
            "catalog_id": item.get("catalog_id"),
            "updated_at": item.get("updated_at"),
            "file_size": item.get("file_size"),
        }

    @staticmethod
    def _file_id(file_id: str | DocumentsFileIdArgs) -> str:
        if isinstance(file_id, DocumentsFileIdArgs):
            return file_id.file_id.strip()
        return file_id.strip()

    @staticmethod
    def _catalog_id(catalog_id: str | DocumentsCatalogIdArgs) -> str:
        if isinstance(catalog_id, DocumentsCatalogIdArgs):
            return catalog_id.catalog_id.strip()
        return catalog_id.strip()

    @staticmethod
    def _access_path(resource_kind: AccessResourceKind, resource_id: str) -> str:
        rid = quote(resource_id, safe="")
        if resource_kind == "catalog":
            return f"{_API}/catalogs/{rid}/access"
        return f"{_API}/documents/{rid}/access"

    async def bind_file(self, placement: DocsPlacement) -> DocsBindResult:
        body: JsonObject = require_json_object(
            placement.model_dump(mode="json"),
            "DocsPlacement",
        )
        response = await self._http.post(
            "office",
            f"{_API}/documents/bind",
            json=body,
            timeout=8.0,
        )
        payload = require_json_object(response, "DocumentsClient.bind_file")
        return DocsBindResult.model_validate(payload)

    async def from_file(
        self,
        file_id: str | DocumentsFromFileArgs,
        title: str | None = None,
        catalog_id: str | None = None,
    ) -> JsonObject:
        if isinstance(file_id, DocumentsFromFileArgs):
            args = file_id
        else:
            args = DocumentsFromFileArgs(file_id=file_id, title=title, catalog_id=catalog_id)
        payload: JsonObject = {"file_id": args.file_id}
        if args.title is not None and args.title.strip():
            payload["title"] = args.title.strip()
        if args.catalog_id is not None and args.catalog_id.strip():
            payload["catalog_id"] = args.catalog_id.strip()
        raw = await self._http.post(
            "office",
            f"{_API}/documents",
            json=payload,
            headers=self._ns_headers(),
        )
        return require_json_object(raw, "documents.create_from_file")

    async def replace_text(
        self,
        file_id: str | DocumentsReplaceTextMutationArgs,
        find: str = "",
        replace: str = "",
        match_case: bool = False,
        tool_call_id: str | None = None,
    ) -> JsonObject:
        if isinstance(file_id, DocumentsReplaceTextMutationArgs):
            args = file_id
        else:
            args = DocumentsReplaceTextMutationArgs(
                file_id=file_id,
                find=find,
                replace=replace,
                match_case=match_case,
                tool_call_id=tool_call_id,
            )
        payload: JsonObject = {
            "find": args.find,
            "replace": args.replace,
            "match_case": args.match_case,
            "tool_call_id": args.tool_call_id,
        }
        return await self._mutate(args.file_id, "mutations/replace-text", payload)

    async def append_text(
        self,
        file_id: str | DocumentsAppendTextMutationArgs,
        text: str = "",
        tool_call_id: str | None = None,
    ) -> JsonObject:
        if isinstance(file_id, DocumentsAppendTextMutationArgs):
            args = file_id
        else:
            args = DocumentsAppendTextMutationArgs(
                file_id=file_id,
                text=text,
                tool_call_id=tool_call_id,
            )
        payload: JsonObject = {"text": args.text, "tool_call_id": args.tool_call_id}
        return await self._mutate(args.file_id, "mutations/append-text", payload)

    async def update_cells(
        self,
        file_id: str | DocumentsUpdateCellsMutationArgs,
        cells: dict[str, CellValue] | None = None,
        sheet: str | None = None,
        tool_call_id: str | None = None,
    ) -> JsonObject:
        if isinstance(file_id, DocumentsUpdateCellsMutationArgs):
            args = file_id
        else:
            if cells is None:
                raise ValueError("cells is required")
            args = DocumentsUpdateCellsMutationArgs(
                file_id=file_id,
                cells=cells,
                sheet=sheet,
                tool_call_id=tool_call_id,
            )
        cells_payload = require_json_object(
            dict(args.cells),
            "documents.update_cells.cells",
        )
        payload: JsonObject = {
            "cells": cells_payload,
            "sheet": args.sheet,
            "tool_call_id": args.tool_call_id,
        }
        return await self._mutate(args.file_id, "mutations/update-cells", payload)

    async def _mutate(
        self,
        file_id: str,
        mutation_path: str,
        payload: JsonObject,
    ) -> JsonObject:
        fid = file_id.strip()
        raw = await self._http.post(
            "office",
            f"{_API}/documents/{quote(fid, safe='')}/{mutation_path}",
            json=payload,
            headers=self._ns_headers(),
            timeout=60.0,
        )
        return require_json_object(raw, "documents.mutation")

    async def create_empty(
        self,
        title: str | DocumentsCreateEmptyArgs,
        catalog_id: str = "",
        document_type: DocumentType = "word",
        spreadsheet_format: SpreadsheetFormat | None = None,
    ) -> JsonObject:
        if isinstance(title, DocumentsCreateEmptyArgs):
            args = title
        else:
            args = DocumentsCreateEmptyArgs(
                title=title,
                catalog_id=catalog_id,
                document_type=document_type,
                spreadsheet_format=spreadsheet_format,
            )
        body: JsonObject = {
            "title": args.title,
            "document_type": args.document_type,
            "catalog_id": args.catalog_id,
        }
        if args.spreadsheet_format is not None:
            body["spreadsheet_format"] = args.spreadsheet_format
        raw = await self._http.post(
            "office",
            f"{_API}/documents/empty",
            json=body,
            headers=self._ns_headers(),
        )
        result = require_json_object(raw, "documents.create_empty")
        return {
            "file_id": result.get("file_id"),
            "catalog_id": result.get("catalog_id"),
            "title": result.get("title"),
            "file_category": result.get("file_category"),
            "onlyoffice_document_type": result.get("onlyoffice_document_type"),
            "editor_url": result.get("editor_url"),
        }

    async def rename(
        self,
        file_id: str | DocumentsRenameArgs,
        title: str = "",
    ) -> JsonObject:
        if isinstance(file_id, DocumentsRenameArgs):
            args = file_id
        else:
            args = DocumentsRenameArgs(file_id=file_id, title=title)
        raw = await self._http.patch(
            "office",
            f"{_API}/documents/{quote(args.file_id, safe='')}",
            json={"title": args.title},
            headers=self._ns_headers(),
        )
        result = require_json_object(raw, "documents.rename")
        return {
            "file_id": result.get("file_id"),
            "title": result.get("title"),
        }

    async def move(
        self,
        file_id: str | DocumentsMoveArgs,
        catalog_id: str = "",
    ) -> JsonObject:
        if isinstance(file_id, DocumentsMoveArgs):
            args = file_id
        else:
            args = DocumentsMoveArgs(file_id=file_id, catalog_id=catalog_id)
        raw = await self._http.post(
            "office",
            f"{_API}/documents/{quote(args.file_id, safe='')}/move",
            json={"catalog_id": args.catalog_id},
            headers=self._ns_headers(),
        )
        result = require_json_object(raw, "documents.move")
        return self._document_item_brief(result)

    async def copy(
        self,
        file_id: str | DocumentsCopyArgs,
        catalog_id: str = "",
        title: str | None = None,
    ) -> JsonObject:
        if isinstance(file_id, DocumentsCopyArgs):
            args = file_id
        else:
            args = DocumentsCopyArgs(file_id=file_id, catalog_id=catalog_id, title=title)
        body: JsonObject = {"catalog_id": args.catalog_id}
        if args.title is not None:
            body["title"] = args.title
        raw = await self._http.post(
            "office",
            f"{_API}/documents/{quote(args.file_id, safe='')}/copy",
            json=body,
            headers=self._ns_headers(),
        )
        result = require_json_object(raw, "documents.copy")
        return {
            "file_id": result.get("file_id"),
            "catalog_id": result.get("catalog_id"),
            "title": result.get("title"),
            "editor_url": result.get("editor_url"),
            "source_file_id": args.file_id,
        }

    async def delete(self, file_id: str | DocumentsFileIdArgs) -> JsonObject:
        fid = self._file_id(file_id)
        _ = await self._http.delete(
            "office",
            f"{_API}/documents/{quote(fid, safe='')}",
            headers=self._ns_headers(),
        )
        return {"file_id": fid, "deleted": True}

    async def list_deleted(self) -> JsonObject:
        raw = await self._http.get(
            "office",
            f"{_API}/documents/deleted",
            headers=self._ns_headers(),
        )
        body = require_json_object(raw, "documents.list_deleted")
        items = [
            self._document_item_brief(item)
            for item in self._as_objects(body.get("items"), "documents.list_deleted.items")
        ]
        return {"count": len(items), "items": items}

    async def restore(self, file_id: str | DocumentsFileIdArgs) -> JsonObject:
        fid = self._file_id(file_id)
        raw = await self._http.post(
            "office",
            f"{_API}/documents/{quote(fid, safe='')}/restore",
            headers=self._ns_headers(),
        )
        result = require_json_object(raw, "documents.restore")
        return self._document_item_brief(result)

    async def permanent_delete(self, file_id: str | DocumentsFileIdArgs) -> JsonObject:
        fid = self._file_id(file_id)
        _ = await self._http.delete(
            "office",
            f"{_API}/documents/{quote(fid, safe='')}/permanent",
            headers=self._ns_headers(),
        )
        return {"file_id": fid, "permanently_deleted": True}

    async def _list_all_catalogs(self) -> list[JsonObject]:
        raw = await self._http.get(
            "office",
            f"{_API}/catalogs",
            headers=self._ns_headers(),
        )
        body = require_json_object(raw, "documents.catalogs")
        return self._as_objects(body.get("items"), "documents.catalogs.items")

    async def _list_documents_in_catalog(
        self,
        catalog_id: str,
        *,
        query: str | None = None,
    ) -> list[JsonObject]:
        params: dict[str, str] = {"catalog_id": catalog_id}
        if query is not None and query.strip() != "":
            params["q"] = query.strip()
        raw = await self._http.get(
            "office",
            f"{_API}/documents",
            headers=self._ns_headers(),
            params=params,
        )
        body = require_json_object(raw, "documents.list")
        return self._as_objects(body.get("items"), "documents.list.items")

    async def _catalog_by_id(self, catalog_id: str) -> JsonObject:
        for item in await self._list_all_catalogs():
            cid = item.get("catalog_id")
            if isinstance(cid, str) and cid == catalog_id:
                return item
        raise ValueError(f"catalog_id not found or not accessible: {catalog_id}")

    async def list_catalog(
        self,
        catalog_id: str | DocumentsListCatalogArgs | None = None,
    ) -> JsonObject:
        if isinstance(catalog_id, DocumentsListCatalogArgs):
            resolved_raw = catalog_id.catalog_id
        else:
            resolved_raw = catalog_id
        catalogs = await self._list_all_catalogs()
        resolved = (
            resolved_raw.strip()
            if isinstance(resolved_raw, str) and resolved_raw.strip()
            else None
        )
        if resolved is None:
            root_catalogs = [
                self._catalog_summary(item)
                for item in catalogs
                if item.get("parent_catalog_id") is None
            ]
            return {
                "catalog_id": None,
                "catalogs": root_catalogs,
                "documents": [],
            }
        child_catalogs = [
            self._catalog_summary(item)
            for item in catalogs
            if item.get("parent_catalog_id") == resolved
        ]
        documents = [
            self._document_summary(item)
            for item in await self._list_documents_in_catalog(resolved)
        ]
        return {
            "catalog_id": resolved,
            "catalogs": child_catalogs,
            "documents": documents,
        }

    async def find(
        self,
        query: str | DocumentsFindArgs,
        catalog_id: str | None = None,
        mode: FindMode = "auto",
        limit: int = 20,
    ) -> JsonObject:
        if isinstance(query, DocumentsFindArgs):
            args = query
        else:
            args = DocumentsFindArgs(
                query=query,
                catalog_id=catalog_id,
                mode=mode,
                limit=limit,
            )
        q = args.query.strip()
        resolved_catalog = (
            args.catalog_id.strip()
            if isinstance(args.catalog_id, str) and args.catalog_id.strip()
            else None
        )

        use_semantic = False
        if args.mode == "semantic":
            use_semantic = True
        elif args.mode == "auto" and resolved_catalog is not None:
            catalog = await self._catalog_by_id(resolved_catalog)
            use_semantic = catalog.get("rag_index_enabled") is True

        if use_semantic:
            if resolved_catalog is None:
                raise ValueError("catalog_id_required: semantic search requires catalog_id")
            catalog = await self._catalog_by_id(resolved_catalog)
            if catalog.get("rag_index_enabled") is not True:
                raise ValueError(
                    "rag_index_disabled: RAG index is not enabled for this catalog; "
                    + "use mode=lexical or mode=auto"
                )
            raw = await self._http.post(
                "office",
                f"{_API}/catalogs/{quote(resolved_catalog, safe='')}/rag-index/search",
                headers=self._ns_headers(),
                json={"query": q, "limit": args.limit},
            )
            body = require_json_object(raw, "documents.semantic_search")
            hits = self._as_objects(body.get("items"), "documents.semantic_search.items")
            items: list[JsonObject] = []
            for hit in hits:
                items.append(
                    {
                        "file_id": hit.get("file_id"),
                        "title": hit.get("title"),
                        "snippet": hit.get("snippet"),
                        "score": hit.get("score"),
                        "catalog_id": hit.get("catalog_id"),
                    }
                )
            return {
                "mode_used": "semantic",
                "query": q,
                "catalog_id": resolved_catalog,
                "items": items,
            }

        if resolved_catalog is not None:
            docs = await self._list_documents_in_catalog(resolved_catalog, query=q)
        else:
            raw = await self._http.get(
                "office",
                f"{_API}/documents/search",
                headers=self._ns_headers(),
                params={"q": q},
            )
            body = require_json_object(raw, "documents.search")
            docs = self._as_objects(body.get("items"), "documents.search.items")

        items = [self._document_summary(item) for item in docs[: args.limit]]
        return {
            "mode_used": "lexical",
            "query": q,
            "catalog_id": resolved_catalog,
            "items": items,
        }

    async def read(
        self,
        file_id: str | DocumentsReadArgs,
        page_start: int = 0,
        page_end: int = -1,
        budget: int | None = None,
    ) -> JsonObject:
        if isinstance(file_id, DocumentsReadArgs):
            args = file_id
        else:
            kwargs: dict[str, JsonValue] = {
                "file_id": file_id,
                "page_start": page_start,
                "page_end": page_end,
            }
            if budget is not None:
                kwargs["budget"] = budget
            args = DocumentsReadArgs.model_validate(kwargs)
        resolved_file = args.file_id.strip()
        files_client = FilesClient(service="office")
        record = await files_client.get_record(resolved_file)
        title = record.original_name
        content_type = record.content_type
        file_size = record.file_size

        file_ref = FileRef(
            file_id=resolved_file,
            original_name=title,
            url=record.url,
            content_type=content_type,
            file_size=file_size,
        )
        read_args = ReadFileArgs(
            names=[title],
            page_start=args.page_start,
            page_end=args.page_end,
            compression=CompressionMode.NEVER,
            budget=args.budget,
        )
        envelope = await read_files_to_envelope(
            [file_ref],
            read_args,
            tool_name="documents_read",
        )
        payload = require_json_object(envelope.model_dump(mode="json"), "documents.read.envelope")
        return {
            "file_id": resolved_file,
            "title": title,
            "envelope": payload,
        }

    async def get_link(
        self,
        file_id: str | DocumentsGetLinkArgs,
        kind: LinkKind = "editor",
    ) -> JsonObject:
        if isinstance(file_id, DocumentsGetLinkArgs):
            args = file_id
        else:
            args = DocumentsGetLinkArgs(file_id=file_id, kind=kind)
        namespace = resolve_namespace_or_raise()
        fid = args.file_id.strip()
        editor_path = (
            f"/documents/edit/{quote(fid, safe='')}?namespace={quote(namespace, safe='')}"
        )
        if args.kind == "editor":
            return {
                "file_id": fid,
                "kind": "editor",
                "url": editor_path,
            }
        raw = await self._http.get(
            "office",
            f"{_API}/documents/{quote(fid, safe='')}/preview",
            headers=self._ns_headers(),
        )
        body = require_json_object(raw, "documents.preview")
        preview_url = body.get("preview_url")
        if not isinstance(preview_url, str) or not preview_url.strip():
            raise ValueError(
                f"preview_url is empty for this document; editor_url={editor_path}"
            )
        return {
            "file_id": fid,
            "kind": "preview",
            "url": preview_url.strip(),
            "editor_url": editor_path,
        }

    async def create_catalog(
        self,
        title: str | DocumentsCreateCatalogArgs,
        company_visible: bool = True,
        parent_catalog_id: str | None = None,
    ) -> JsonObject:
        if isinstance(title, DocumentsCreateCatalogArgs):
            args = title
        else:
            args = DocumentsCreateCatalogArgs(
                title=title,
                company_visible=company_visible,
                parent_catalog_id=parent_catalog_id,
            )
        body: JsonObject = {"title": args.title, "company_visible": args.company_visible}
        if args.parent_catalog_id is not None:
            body["parent_catalog_id"] = args.parent_catalog_id
        raw = await self._http.post(
            "office",
            f"{_API}/catalogs",
            headers=self._ns_headers(),
            json=body,
        )
        result = require_json_object(raw, "documents.create_catalog")
        return {
            "catalog_id": result.get("catalog_id"),
            "title": result.get("title"),
            "parent_catalog_id": result.get("parent_catalog_id"),
            "company_visible": result.get("company_visible"),
            "is_owner": result.get("is_owner"),
        }

    async def update_catalog(
        self,
        catalog_id: str | DocumentsUpdateCatalogArgs,
        title: str | None = None,
        company_visible: bool | None = None,
    ) -> JsonObject:
        if isinstance(catalog_id, DocumentsUpdateCatalogArgs):
            args = catalog_id
        else:
            args = DocumentsUpdateCatalogArgs(
                catalog_id=catalog_id,
                title=title,
                company_visible=company_visible,
            )
        body: JsonObject = {}
        if args.title is not None:
            body["title"] = args.title
        if args.company_visible is not None:
            body["company_visible"] = args.company_visible
        if not body:
            raise ValueError("Provide title and/or company_visible")
        raw = await self._http.patch(
            "office",
            f"{_API}/catalogs/{quote(args.catalog_id, safe='')}",
            headers=self._ns_headers(),
            json=body,
        )
        result = require_json_object(raw, "documents.update_catalog")
        return {
            "catalog_id": result.get("catalog_id"),
            "title": result.get("title"),
            "company_visible": result.get("company_visible"),
            "is_owner": result.get("is_owner"),
        }

    async def list_catalog_members(
        self,
        catalog_id: str | DocumentsCatalogIdArgs,
    ) -> JsonObject:
        cid = self._catalog_id(catalog_id)
        raw = await self._http.get(
            "office",
            f"{_API}/catalogs/{quote(cid, safe='')}/members",
            headers=self._ns_headers(),
        )
        body = require_json_object(raw, "documents.catalog_members")
        items = self._as_objects(body.get("members"), "documents.catalog_members.members")
        return {
            "catalog_id": cid,
            "items": [
                {
                    "user_id": item.get("user_id"),
                    "display_name": item.get("display_name"),
                }
                for item in items
            ],
        }

    async def add_catalog_member(
        self,
        catalog_id: str | DocumentsAddCatalogMemberArgs,
        user_id: str = "",
    ) -> JsonObject:
        if isinstance(catalog_id, DocumentsAddCatalogMemberArgs):
            args = catalog_id
        else:
            args = DocumentsAddCatalogMemberArgs(catalog_id=catalog_id, user_id=user_id)
        raw = await self._http.post(
            "office",
            f"{_API}/catalogs/{quote(args.catalog_id, safe='')}/members",
            headers=self._ns_headers(),
            json={"user_id": args.user_id},
        )
        body = require_json_object(raw, "documents.add_catalog_member")
        items = self._as_objects(body.get("members"), "documents.add_catalog_member.members")
        return {
            "catalog_id": args.catalog_id,
            "user_id": args.user_id,
            "items": [
                {
                    "user_id": item.get("user_id"),
                    "display_name": item.get("display_name"),
                }
                for item in items
            ],
        }

    async def get_access(
        self,
        resource_kind: AccessResourceKind | DocumentsAccessArgs,
        resource_id: str = "",
    ) -> JsonObject:
        if isinstance(resource_kind, DocumentsAccessArgs):
            args = resource_kind
        else:
            args = DocumentsAccessArgs(resource_kind=resource_kind, resource_id=resource_id)
        raw = await self._http.get(
            "office",
            self._access_path(args.resource_kind, args.resource_id),
            headers=self._ns_headers(),
        )
        return require_json_object(raw, "documents.get_access")

    async def patch_access(
        self,
        resource_kind: AccessResourceKind | DocumentsPatchAccessArgs,
        resource_id: str = "",
        company_visible: bool | None = None,
        link_enabled: bool | None = None,
        link_permission: Literal["viewer", "editor"] | None = None,
        members: list[DocumentsAccessMemberItem] | None = None,
    ) -> JsonObject:
        if isinstance(resource_kind, DocumentsPatchAccessArgs):
            args = resource_kind
        else:
            args = DocumentsPatchAccessArgs(
                resource_kind=resource_kind,
                resource_id=resource_id,
                company_visible=company_visible,
                link_enabled=link_enabled,
                link_permission=link_permission,
                members=members,
            )
        body: JsonObject = {}
        if args.company_visible is not None:
            body["company_visible"] = args.company_visible
        if args.link_enabled is not None:
            body["link_enabled"] = args.link_enabled
        if args.link_permission is not None:
            body["link_permission"] = args.link_permission
        if args.members is not None:
            body["members"] = [
                {"user_id": member.user_id, "relation": member.relation}
                for member in args.members
            ]
        if not body:
            raise ValueError("Provide at least one access field to patch")
        raw = await self._http.patch(
            "office",
            self._access_path(args.resource_kind, args.resource_id),
            headers=self._ns_headers(),
            json=body,
        )
        return require_json_object(raw, "documents.patch_access")

    async def rotate_public_link(
        self,
        resource_kind: AccessResourceKind | DocumentsAccessArgs,
        resource_id: str = "",
    ) -> JsonObject:
        if isinstance(resource_kind, DocumentsAccessArgs):
            args = resource_kind
        else:
            args = DocumentsAccessArgs(resource_kind=resource_kind, resource_id=resource_id)
        raw = await self._http.post(
            "office",
            f"{self._access_path(args.resource_kind, args.resource_id)}/link/rotate",
            headers=self._ns_headers(),
        )
        result = require_json_object(raw, "documents.rotate_public_link")
        return {
            "resource_kind": args.resource_kind,
            "resource_id": args.resource_id,
            "public_url": result.get("public_url"),
        }

    async def catalog_rag_status(
        self,
        catalog_id: str | DocumentsCatalogIdArgs,
    ) -> JsonObject:
        cid = self._catalog_id(catalog_id)
        raw = await self._http.get(
            "office",
            f"{_API}/catalogs/{quote(cid, safe='')}/rag-index/status",
            headers=self._ns_headers(),
        )
        result = require_json_object(raw, "documents.catalog_rag_status")
        return {"catalog_id": cid, **result}

    async def catalog_rag_enable(
        self,
        catalog_id: str | DocumentsCatalogIdArgs,
    ) -> JsonObject:
        cid = self._catalog_id(catalog_id)
        raw = await self._http.post(
            "office",
            f"{_API}/catalogs/{quote(cid, safe='')}/rag-index/enable",
            headers=self._ns_headers(),
        )
        result = require_json_object(raw, "documents.catalog_rag_enable")
        return {"catalog_id": cid, **result}

    async def catalog_rag_disable(
        self,
        catalog_id: str | DocumentsCatalogIdArgs,
    ) -> JsonObject:
        cid = self._catalog_id(catalog_id)
        raw = await self._http.post(
            "office",
            f"{_API}/catalogs/{quote(cid, safe='')}/rag-index/disable",
            headers=self._ns_headers(),
        )
        result = require_json_object(raw, "documents.catalog_rag_disable")
        return {"catalog_id": cid, **result}

    async def catalog_rag_rebuild(
        self,
        catalog_id: str | DocumentsCatalogIdArgs,
    ) -> JsonObject:
        cid = self._catalog_id(catalog_id)
        raw = await self._http.post(
            "office",
            f"{_API}/catalogs/{quote(cid, safe='')}/rag-index/rebuild",
            headers=self._ns_headers(),
        )
        result = require_json_object(raw, "documents.catalog_rag_rebuild")
        return {"catalog_id": cid, **result}
