"""Размещение файла в дереве: цепочка каталогов и строка FileRecord в одной транзакции."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from oxyde import atomic

from core.authz.models import AuthzObject, AuthzSubject, AuthzTuple
from core.authz.service import AuthzService
from core.authz.types import AuthzRelation
from core.documents.authz.tuples import (
    document_catalog_company_link,
    document_catalog_company_viewer_tuple,
    document_catalog_lister_tuple,
    document_catalog_owner_tuple,
    document_catalog_parent_tuple,
    document_catalog_source_tuple,
    document_file_catalog_link,
    document_file_owner_tuple,
    document_file_source_tuple,
)
from core.documents.catalog import DocumentCatalog
from core.documents.names import autorename, name_key, split_catalog_path, validate_original_name
from core.documents.paths import SourceAnchor, placed_path, source_anchor, source_object_key
from core.documents.placement import DocumentPlacement
from core.errors.boundary import (
    PlatformAccessDeniedError,
    PlatformConflictError,
    PlatformNotFoundError,
)
from core.files.create_spec import FileSourceKind, FileSourceRef
from core.files.models import FileRecord
from core.files.registry import is_docs_placement_exempt

_NAME_ATTEMPTS = 50


@dataclass(frozen=True, slots=True)
class PlaceResult:
    record: FileRecord
    created_catalogs: list[DocumentCatalog]
    source: AuthzObject | None


class DocumentTreeService:
    def __init__(self, authz: AuthzService) -> None:
        self._authz: AuthzService = authz

    async def place(
        self,
        record: FileRecord,
        *,
        source_kind: FileSourceKind,
        source_ref: FileSourceRef,
        placement: DocumentPlacement | None,
        namespace: str,
        user_id: str,
    ) -> PlaceResult:
        if is_docs_placement_exempt(source_kind):
            if source_kind is FileSourceKind.OFFICE_DOCUMENT:
                return await self._place_office(
                    record,
                    placement=placement,
                    namespace=namespace,
                    user_id=user_id,
                )
            stored = record.model_copy(update={"source_kind": source_kind.value, "catalog_id": None})
            _ = await FileRecord.set(stored)
            return PlaceResult(record=stored, created_catalogs=[], source=None)
        company_id = record.company_id
        if company_id is None or company_id == "":
            raise ValueError("company_id is required")
        path = placed_path(source_kind, source_ref)
        anchor = source_anchor(source_kind, source_ref, company_id=company_id)
        return await self._place_at(
            record,
            company_id=company_id,
            namespace=namespace,
            user_id=user_id,
            source_kind=source_kind,
            segments=path,
            anchor=anchor,
            managed=True,
            conflict="autorename",
            dedupe_identical=True,
            start_catalog_id=None,
        )

    async def ensure_path(
        self,
        *,
        company_id: str,
        namespace: str,
        user_id: str,
        parent_catalog_id: str | None,
        catalog_path: list[str],
        company_visible: bool,
    ) -> DocumentCatalog:
        segments = split_catalog_path(catalog_path)
        if not segments:
            raise ValueError("catalog_path is required")
        created: list[DocumentCatalog] = []
        parent_id = parent_catalog_id
        last: DocumentCatalog | None = None
        for index, segment in enumerate(segments):
            visible = company_visible and parent_id is None and index == 0
            catalog, was_created = await DocumentCatalog.ensure_child(
                company_id=company_id,
                namespace=namespace,
                parent_catalog_id=parent_id,
                title=segment,
                owner_user_id=user_id,
                managed=False,
                source_object=None,
                company_visible=visible,
            )
            if was_created:
                created.append(catalog)
            parent_id = catalog.catalog_id
            last = catalog
        if last is None:
            raise RuntimeError("ensure_path produced no catalog")
        await self._sync_created(created, source=None)
        return last

    async def _place_office(
        self,
        record: FileRecord,
        *,
        placement: DocumentPlacement | None,
        namespace: str,
        user_id: str,
    ) -> PlaceResult:
        if placement is None:
            raise ValueError("office document requires placement")
        company_id = record.company_id
        if company_id is None or company_id == "":
            raise ValueError("company_id is required")
        segments = split_catalog_path(placement.catalog_path)
        return await self._place_at(
            record,
            company_id=company_id,
            namespace=namespace,
            user_id=user_id,
            source_kind=FileSourceKind.OFFICE_DOCUMENT,
            segments=segments,
            anchor=None,
            managed=False,
            conflict=placement.conflict,
            start_catalog_id=placement.catalog_id,
        )

    async def _place_at(
        self,
        record: FileRecord,
        *,
        company_id: str,
        namespace: str,
        user_id: str,
        source_kind: FileSourceKind,
        segments: list[str],
        anchor: SourceAnchor | None,
        managed: bool,
        conflict: str,
        dedupe_identical: bool = False,
        start_catalog_id: str | None,
    ) -> PlaceResult:
        original_name = validate_original_name(record.original_name)
        created: list[DocumentCatalog] = []
        source = anchor.source if anchor is not None else None
        async with atomic(using="shared"):
            parent_id = start_catalog_id
            if parent_id is not None:
                parent = await DocumentCatalog.catalog_in_namespace(parent_id, company_id, namespace)
                if parent is None:
                    raise PlatformNotFoundError(f"catalog not found: {parent_id}")
            for index, segment in enumerate(segments):
                source_object = None
                company_visible = False
                if anchor is not None and index == anchor.index:
                    if anchor.source is not None:
                        source_object = source_object_key(anchor.source)
                    company_visible = anchor.company_visible
                catalog, was_created = await DocumentCatalog.ensure_child(
                    company_id=company_id,
                    namespace=namespace,
                    parent_catalog_id=parent_id,
                    title=segment,
                    owner_user_id=user_id,
                    managed=managed,
                    source_object=source_object,
                    company_visible=company_visible,
                )
                if was_created:
                    created.append(catalog)
                parent_id = catalog.catalog_id
            if parent_id is None:
                raise ValueError("document requires a catalog")
            chosen = await self._claim_name(
                record,
                company_id=company_id,
                catalog_id=parent_id,
                original_name=original_name,
                source_kind=source_kind,
                conflict=conflict,
                dedupe_identical=dedupe_identical,
            )
        await self._sync_created(created, source=source)
        await self._sync_file(chosen, user_id=user_id, source=source)
        return PlaceResult(record=chosen, created_catalogs=created, source=source)

    async def _claim_name(
        self,
        record: FileRecord,
        *,
        company_id: str,
        catalog_id: str,
        original_name: str,
        source_kind: FileSourceKind,
        conflict: str,
        dedupe_identical: bool = False,
    ) -> FileRecord:
        for attempt in range(_NAME_ATTEMPTS):
            candidate = original_name if attempt == 0 else autorename(original_name, attempt)
            key = name_key(candidate)
            existing = await FileRecord.objects.filter(
                catalog_id=catalog_id,
                name_key=key,
                deleted_at=None,
            ).get_or_none()
            if existing is not None:
                if (
                    dedupe_identical
                    and existing.source_kind == source_kind.value
                    and existing.checksum is not None
                    and existing.checksum == record.checksum
                ):
                    return existing
                if conflict == "fail":
                    raise PlatformConflictError(f"name already exists: {candidate}")
                if conflict == "replace" and attempt == 0:
                    raise PlatformConflictError(f"replace target: {existing.file_id}")
                continue
            stored = record.model_copy(
                update={
                    "original_name": candidate,
                    "source_kind": source_kind.value,
                    "catalog_id": catalog_id,
                    "name_key": key,
                    "company_id": company_id,
                }
            )
            _ = await FileRecord.set(stored)
            return stored
        raise PlatformConflictError(f"could not place {original_name}")

    async def _sync_created(self, created: list[DocumentCatalog], *, source: AuthzObject | None) -> None:
        now = datetime.now(timezone.utc)
        try:
            for catalog in created:
                writes = self._catalog_tuples(catalog, source=source)
                await self._authz.write(writes)
                await DocumentCatalog.mark_authz_synced(catalog.catalog_id, now)
        except Exception:
            for catalog in reversed(created):
                _ = await DocumentCatalog.delete_in_namespace(
                    catalog.catalog_id,
                    catalog.company_id,
                    catalog.namespace,
                )
            raise

    def _catalog_tuples(self, catalog: DocumentCatalog, *, source: AuthzObject | None) -> list[AuthzTuple]:
        writes = [
            document_catalog_owner_tuple(catalog.catalog_id, catalog.owner_user_id),
            document_catalog_company_link(catalog.catalog_id, catalog.company_id),
        ]
        if catalog.parent_catalog_id is None:
            if catalog.company_visible or catalog.managed:
                writes.append(
                    document_catalog_lister_tuple(catalog.catalog_id, catalog.company_id)
                )
        else:
            writes.append(document_catalog_parent_tuple(catalog.catalog_id, catalog.parent_catalog_id))
        if catalog.company_visible:
            writes.append(document_catalog_company_viewer_tuple(catalog.catalog_id, catalog.company_id))
        if catalog.source_object is not None and source is not None and source.fga_id == catalog.source_object:
            writes.append(document_catalog_source_tuple(catalog.catalog_id, source))
        return writes

    async def _sync_file(self, record: FileRecord, *, user_id: str, source: AuthzObject | None) -> None:
        if record.catalog_id is None:
            return
        owner = record.uploaded_by if record.uploaded_by else user_id
        writes = [
            document_file_owner_tuple(record.file_id, owner),
            document_file_catalog_link(record.file_id, record.catalog_id),
        ]
        if source is not None:
            writes.append(document_file_source_tuple(record.file_id, source))
        await self._authz.write(writes)
        now = datetime.now(timezone.utc)
        _ = await FileRecord.objects.filter(file_id=record.file_id).update(authz_synced_at=now)

    async def require_catalog_edit(self, catalog_id: str, user_id: str) -> None:
        await self._authz.require_can_edit(AuthzObject.document_catalog(catalog_id), user_id=user_id)

    async def user_can_edit_source(self, source: AuthzObject, user_id: str) -> bool:
        return await self._authz.can_edit(source, user_id=user_id)

    async def authorize_placement(
        self,
        *,
        user_id: str,
        company_id: str,
        namespace: str,
        source_kind: FileSourceKind,
        source_ref: FileSourceRef,
        placement: DocumentPlacement | None,
    ) -> None:
        _ = namespace
        if is_docs_placement_exempt(source_kind) and source_kind is not FileSourceKind.OFFICE_DOCUMENT:
            return
        if source_kind is FileSourceKind.OFFICE_DOCUMENT:
            if placement is None or placement.catalog_id is None:
                return
            await self.require_catalog_edit(placement.catalog_id, user_id)
            return
        anchor = source_anchor(source_kind, source_ref, company_id=company_id)
        if anchor.source is None:
            return
        allowed = await self._authz.can_edit(anchor.source, user_id=user_id)
        if not allowed:
            raise PlatformAccessDeniedError("no access to place a file for this source")

    async def move_file(
        self,
        record: FileRecord,
        *,
        catalog_id: str,
        original_name: str | None,
        conflict: str,
        namespace: str,
    ) -> FileRecord:
        if record.company_id is None:
            raise PlatformNotFoundError("file has no company")
        if record.catalog_id is None:
            raise PlatformConflictError("file is not in the document tree")
        name = validate_original_name(original_name if original_name else record.original_name)
        key = name_key(name)
        target = await DocumentCatalog.catalog_in_namespace(catalog_id, record.company_id, namespace)
        if target is None:
            raise PlatformNotFoundError("catalog not found")
        existing = await FileRecord.objects.filter(
            catalog_id=catalog_id,
            name_key=key,
            deleted_at=None,
        ).get_or_none()
        if existing is not None and existing.file_id != record.file_id:
            if conflict == "fail":
                raise PlatformConflictError(f"name already exists: {name}")
            name = autorename(name, 1)
            key = name_key(name)
        old_catalog_id = record.catalog_id
        moved = record.model_copy(
            update={"catalog_id": catalog_id, "original_name": name, "name_key": key}
        )
        _ = await FileRecord.set(moved)
        if old_catalog_id != catalog_id:
            await self._authz.write_and_delete(
                [document_file_catalog_link(record.file_id, catalog_id)],
                [document_file_catalog_link(record.file_id, old_catalog_id)],
            )
        return moved

    async def sync_pending_authz(self, *, limit: int) -> int:
        catalogs = await DocumentCatalog.list_pending_authz_by_created_at_asc(limit=limit)
        synced = 0
        for catalog in catalogs:
            source = None
            if catalog.source_object is not None:
                source = AuthzObject.from_fga_id(catalog.source_object)
            await self._authz.write(self._catalog_tuples(catalog, source=source))
            await DocumentCatalog.mark_authz_synced(catalog.catalog_id, datetime.now(timezone.utc))
            synced += 1
        files = await FileRecord.list_pending_authz_with_catalog_by_created_at_asc(limit=limit)
        for record in files:
            if record.catalog_id is None or record.uploaded_by is None:
                continue
            await self._sync_file(record, user_id=record.uploaded_by, source=None)
            synced += 1
        return synced

    async def can_list_catalog(self, catalog_id: str, user_id: str) -> bool:
        return await self._authz.check(
            AuthzSubject.user(user_id),
            AuthzRelation.CAN_LIST,
            AuthzObject.document_catalog(catalog_id),
        )
