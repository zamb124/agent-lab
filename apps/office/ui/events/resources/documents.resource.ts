/**
 * Office Documents — привязки документов OnlyOffice к каталогам.
 *
 * Backend (`/documents/api/v1/documents` + nested):
 *   GET    /documents?catalog_ids=...        → OfficeDocumentListResponse { items }
 *   POST   /documents                        → OfficeDocumentCreateResponse (JSON: file_id, title?, catalog_id?)
 *   POST   /documents/empty                  → OfficeDocumentCreateResponse (JSON: title, document_type, catalog_id, spreadsheet_format?)
 *   PATCH  /documents/{file_id}              → OfficeDocumentRenameResponse (JSON: title)
 *   DELETE /documents/{file_id}              → 204
 *
 * `documentsOp` — list по `catalog_ids` (sub-resource), slice хранит
 * `items` + `loadedCatalogIds` + `activeCatalogId` + `filterCatalogIds`.
 * `activeCatalogId === null` в режиме `catalog` — корень namespace (корневые
 * каталоги в главной панели, без GET /documents). Файл без каталога запрещён.
 *
 * `documentRenameForm` — форма для модалки `office.document_rename`,
 * submitEvent → `documentRenameOp.events.REQUESTED`.
 */

import { createAsyncOp, createForm } from '@platform/lib/events/index.js';
import type { PlatformEvent, EffectCtx } from '@platform/lib/events/contract.js';
import type { DocumentsSlice, OfficeDocumentItem } from '../documents.types.js';
import { isOfficeDocumentItem } from '../documents.types.js';

type EventPayload = Record<string, unknown>;

function uploadJobEvent(events: Readonly<Record<string, string>>, name: string): string {
    const eventName = events[name];
    if (eventName === undefined || eventName.length === 0) {
        throw new Error(`documents: ${name} missing`);
    }
    return eventName;
}
import { httpRequest } from '@platform/lib/events/http.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { platformStorageKey } from '@platform/lib/utils/storage-keys.js';
import { storageGet, storageSet, storageSetJson } from '@platform/lib/utils/platform-storage.js';
import { uploadPlatformFile } from '@platform/lib/utils/platform-file-upload.js';
import { buildOfficeDocumentFileCreateSpecJson } from '@platform/lib/utils/file-create-spec.js';
import { nsHeader } from './_namespace-header.js';
import { isJsonObject } from '@platform/lib/utils/json-object.js';
import { isPlatformEventType } from '@platform/lib/events/payload.js';

export type { OfficeDocumentItem, DocumentsSlice } from '../documents.types.js';

const RECENT_STORAGE_KEY = 'documents_explorer_recent_ids';
const STARRED_STORAGE_KEY = 'documents_explorer_starred_ids';
const EXPLORER_VIEW_STORAGE_KEY = 'documents_explorer_view';
const EXPANDED_CATALOGS_STORAGE_KEY = 'documents_explorer_expanded_catalog_ids';
const SEARCH_MODE_STORAGE_KEY = 'documents_explorer_search_mode';
const RECENT_LIMIT = 20;

function _readStoredSearchMode() {
    const raw = storageGet(platformStorageKey('office', SEARCH_MODE_STORAGE_KEY));
    if (raw === 'files' || raw === 'semantic') {
        return raw;
    }
    return 'files';
}

function _readStoredIds(storageKey: string): string[] {
    const raw = storageGet(platformStorageKey('office', storageKey));
    if (typeof raw !== 'string' || raw.length === 0) {
        return [];
    }
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
        throw new Error(`documents: invalid stored ids for ${storageKey}`);
    }
    return parsed.filter((id): id is string => typeof id === 'string' && id.length > 0);
}

function _writeStoredIds(storageKey: string, ids: string[]) {
    storageSetJson(platformStorageKey('office', storageKey), ids);
}

function _normalizeCatalogIds(raw: unknown): string[] {
    if (!Array.isArray(raw)) {
        throw new Error('documents: payload.catalog_ids (array) required');
    }
    const ids: string[] = [];
    const seen = new Set<string>();
    for (const id of raw) {
        const v = typeof id === 'string' ? id.trim() : '';
        if (v.length === 0) continue;
        if (seen.has(v)) continue;
        seen.add(v);
        ids.push(v);
    }
    if (ids.length === 0) {
        throw new Error('documents: payload.catalog_ids must contain at least one non-empty id');
    }
    return ids;
}

function isDocumentsSlice(value: unknown): value is DocumentsSlice {
    return isJsonObject(value);
}

function officeDocuments(state: unknown): DocumentsSlice | null {
    if (!isJsonObject(state)) {
        return null;
    }
    const slice = state.officeDocuments;
    if (slice === undefined || slice === null) {
        return null;
    }
    if (!isDocumentsSlice(slice)) {
        throw new Error('documents: officeDocuments must be an object');
    }
    return slice;
}

const RAG_INDEX_STATUS_VALUES = [
    'ready',
    'pending',
    'failed',
    'absent',
] as const satisfies readonly NonNullable<OfficeDocumentItem['rag_index_status']>[];

function isRagIndexStatus(value: unknown): value is NonNullable<OfficeDocumentItem['rag_index_status']> {
    return typeof value === 'string'
        && (RAG_INDEX_STATUS_VALUES as readonly string[]).includes(value);
}

function documentItems(value: unknown): OfficeDocumentItem[] {
    if (!Array.isArray(value)) {
        throw new Error('office/documents: SUCCEEDED.result.items required (array)');
    }
    const items: OfficeDocumentItem[] = [];
    for (const raw of value) {
        if (!isOfficeDocumentItem(raw)) {
            throw new Error('office/documents: document item must be an OfficeDocumentItem');
        }
        items.push(raw);
    }
    return items;
}

function stringIds(value: unknown): string[] {
    if (!Array.isArray(value)) {
        return [];
    }
    return value.filter((id): id is string => typeof id === 'string' && id.length > 0);
}

function _reloadVisibleDocuments(ctx: EffectCtx, event: PlatformEvent) {
    const docState = officeDocuments(ctx.getState());
    if (!docState) {
        return;
    }
    const filterIds = Array.isArray(docState.filterCatalogIds)
        ? docState.filterCatalogIds.filter((id): id is string => typeof id === 'string' && id.length > 0)
        : [];
    const activeId = typeof docState.activeCatalogId === 'string' && docState.activeCatalogId.length > 0
        ? docState.activeCatalogId
        : '';
    const ids = filterIds.length > 0 ? filterIds : (activeId.length > 0 ? [activeId] : []);
    if (ids.length === 0) {
        return;
    }
    ctx.dispatch(
        documentsOp.events.REQUESTED,
        buildDocumentsListPayload(docState, ids),
        { causation_id: event.id, source: 'local' },
    );
}

const _DOCUMENT_ITEM_COMPARE_KEYS = [
    'catalog_id',
    'title',
    'file_id',
    'file_category',
    'onlyoffice_document_type',
    'file_availability',
    'file_expires_at',
    'file_size',
    'created_at',
    'updated_at',
    'created_by_user_id',
    'created_by_display_name',
    'created_by_avatar_url',
    'rag_index_status',
];

function _documentItemsEqual(left: OfficeDocumentItem, right: OfficeDocumentItem) {
    for (const key of _DOCUMENT_ITEM_COMPARE_KEYS) {
        if (left[key] !== right[key]) {
            return false;
        }
    }
    return true;
}

function _sameCatalogIds(left: unknown, right: unknown) {
    if (!Array.isArray(left) || !Array.isArray(right) || left.length !== right.length) {
        return false;
    }
    return left.every((id, index) => id === right[index]);
}

/**
 * Точечный merge списка: тот же object-ref для неизменённых айтемов,
 * новые/изменённые — новые объекты, удалённые выпадают. Порядок — как у next.
 */
function _mergeDocumentItems(prevItems: OfficeDocumentItem[], nextItems: OfficeDocumentItem[]) {
    const prevById = new Map(
        prevItems.map((item) => [item.file_id, item]),
    );
    const merged: OfficeDocumentItem[] = [];
    for (const nextItem of nextItems) {
        const prevItem = prevById.get(nextItem.file_id);
        if (prevItem && _documentItemsEqual(prevItem, nextItem)) {
            merged.push(prevItem);
            continue;
        }
        merged.push(nextItem);
    }
    return merged;
}

export function buildDocumentsListPayload(docState: DocumentsSlice, catalogIds: unknown) {
    const ids = _normalizeCatalogIds(catalogIds);
    const query = typeof docState.searchQuery === 'string' ? docState.searchQuery.trim() : '';
    return {
        catalog_ids: ids,
        q: query.length > 0 ? query : null,
        sort: docState.sortKey,
        order: docState.sortDir,
    };
}

const DOCUMENTS_ACTIONS = {
    setActiveCatalog:  'set_active_catalog',
    setCatalogExpanded: 'set_catalog_expanded',
    setFilterCatalogs: 'set_filter_catalogs',
    clearFilter:       'clear_filter',
    setViewMode:       'set_view_mode',
    setSearchQuery:    'set_search_query',
    setSearchMode:     'set_search_mode',
    setSort:           'set_sort',
    setSelectedFile: 'set_selected_file',
    setSelectedCatalog: 'set_selected_catalog',
    toggleFileSelection: 'toggle_file_selection',
    setFileSelection: 'set_file_selection',
    clearFileSelection: 'clear_file_selection',
    setExplorerView: 'set_explorer_view',
    toggleStarred: 'toggle_starred',
    recordRecentOpen: 'record_recent_open',
    patchRagIndexStatuses: 'patch_rag_index_statuses',
} as const;

export const documentsOp = createAsyncOp<'office/documents/list_requested', DocumentsSlice, typeof DOCUMENTS_ACTIONS>({
    name: 'office/documents',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'office/documents/list_requested',
    restMirror: { method: 'GET', path: '/documents/api/v1/documents' },
    extraInitial: {
        items: [],
        loadedCatalogIds: [],
        activeCatalogId: null,
        filterCatalogIds: [],
        viewMode: 'list',
        searchQuery: '',
        searchMode: _readStoredSearchMode(),
        sortKey: 'updated_at',
        sortDir: 'desc',
        selectedFileId: null,
        selectedCatalogId: null,
        selectedFileIds: [],
        uploadJobs: [],
        explorerView: 'catalog',
        recentFileIds: _readStoredIds(RECENT_STORAGE_KEY),
        starredFileIds: _readStoredIds(STARRED_STORAGE_KEY),
        expandedCatalogIds: _readStoredIds(EXPANDED_CATALOGS_STORAGE_KEY),
    },
    extraEvents: {
        SET_ACTIVE_CATALOG:  'set_active_catalog',
        SET_CATALOG_EXPANDED: 'set_catalog_expanded',
        SET_FILTER_CATALOGS: 'set_filter_catalogs',
        CLEAR_FILTER:        'clear_filter',
        SET_VIEW_MODE:       'set_view_mode',
        SET_SEARCH_QUERY:    'set_search_query',
        SET_SEARCH_MODE:     'set_search_mode',
        SET_SORT:            'set_sort',
        SET_SELECTED_FILE:   'set_selected_file',
        SET_SELECTED_CATALOG: 'set_selected_catalog',
        TOGGLE_FILE_SELECTION: 'toggle_file_selection',
        SET_FILE_SELECTION:  'set_file_selection',
        CLEAR_FILE_SELECTION: 'clear_file_selection',
        UPLOAD_JOB_ADD:      'upload_job_add',
        UPLOAD_JOB_UPDATE:   'upload_job_update',
        UPLOAD_JOB_REMOVE:   'upload_job_remove',
        SET_EXPLORER_VIEW:   'set_explorer_view',
        TOGGLE_STARRED:      'toggle_starred',
        RECORD_RECENT_OPEN:  'record_recent_open',
        PATCH_RAG_INDEX_STATUSES: 'patch_rag_index_statuses',
    },
    actions: DOCUMENTS_ACTIONS,
    extraReducer: (state: DocumentsSlice, event, events) => {
        const docState = state;
        const payload = isJsonObject(event.payload) ? event.payload : null;
        if (event.type === events.REQUESTED) {
            if (!payload || typeof payload !== 'object') {
                throw new Error('office/documents: REQUESTED.payload required');
            }
            const ids = _normalizeCatalogIds(payload.catalog_ids);
            const items = Array.isArray(docState.items) ? docState.items : [];
            // Soft-refresh того же scope: не обнуляем items (иначе мигает вся таблица).
            if (_sameCatalogIds(ids, docState.loadedCatalogIds) && items.length > 0) {
                return { ...state, loadedCatalogIds: ids };
            }
            return { ...state, items: [], loadedCatalogIds: ids };
        }
        if (event.type === events.SUCCEEDED) {
            const result = payload !== null && isJsonObject(payload.result) ? payload.result : null;
            const nextItems = documentItems(result === null ? undefined : result.items);
            const prevItems = Array.isArray(docState.items) ? docState.items : [];
            if (prevItems.length === 0) {
                return { ...state, items: nextItems };
            }
            return { ...state, items: _mergeDocumentItems(prevItems, nextItems) };
        }
        if (event.type === events.PATCH_RAG_INDEX_STATUSES) {
            const statuses = payload && payload.statuses;
            if (!isJsonObject(statuses)) {
                throw new Error('office/documents: patch_rag_index_statuses.statuses object required');
            }
            let changed = false;
            const prevItems = Array.isArray(docState.items) ? docState.items : [];
            const items = prevItems.map((item) => {
                if (typeof item.file_id !== 'string' || !(item.file_id in statuses)) {
                    return item;
                }
                const nextStatus = statuses[item.file_id];
                if (nextStatus !== null && !isRagIndexStatus(nextStatus)) {
                    throw new Error(
                        `office/documents: invalid rag_index_status '${String(nextStatus)}'`,
                    );
                }
                if (item.rag_index_status === nextStatus) {
                    return item;
                }
                changed = true;
                return { ...item, rag_index_status: nextStatus };
            });
            return changed ? { ...state, items } : state;
        }
        if (isPlatformEventType(event, 'rag/document/status_updated')) {
            const documentId = event.payload.document_id;
            const ragStatus = event.payload.status;
            let nextStatus: OfficeDocumentItem['rag_index_status'] = null;
            if (ragStatus === 'completed') {
                nextStatus = 'ready';
            } else if (ragStatus === 'failed') {
                nextStatus = 'failed';
            } else if (ragStatus === 'processing' || ragStatus === 'pending' || ragStatus === 'queued') {
                nextStatus = 'pending';
            } else {
                return state;
            }
            const prevItems = docState.items;
            if (!Array.isArray(prevItems)) {
                return state;
            }
            let changed = false;
            const items = prevItems.map((item) => {
                if (item.file_id !== documentId) {
                    return item;
                }
                if (item.rag_index_status === nextStatus) {
                    return item;
                }
                changed = true;
                return { ...item, rag_index_status: nextStatus };
            });
            return changed ? { ...state, items } : state;
        }
        if (isPlatformEventType(event, 'office/document/saved')) {
            const fileId = event.payload.file_id;
            const title = typeof event.payload.title === 'string' && event.payload.title.length > 0
                ? event.payload.title
                : null;
            const savedAt = new Date().toISOString();
            const prevItems = docState.items;
            if (!Array.isArray(prevItems)) {
                return state;
            }
            let changed = false;
            const items = prevItems.map((item) => {
                if (item.file_id !== fileId) {
                    return item;
                }
                changed = true;
                const next: OfficeDocumentItem = { ...item, updated_at: savedAt };
                if (title !== null) {
                    next.title = title;
                }
                return next;
            });
            return changed ? { ...state, items } : state;
        }
        if (event.type === events.SET_ACTIVE_CATALOG) {
            const rawCatalogId = payload && payload.catalogId;
            const catalogId = typeof rawCatalogId === 'string' && rawCatalogId.length > 0
                ? rawCatalogId
                : null;
            return {
                ...state,
                activeCatalogId: catalogId,
                selectedCatalogId: null,
            };
        }
        if (event.type === events.SET_CATALOG_EXPANDED) {
            const catalogId = payload && typeof payload.catalogId === 'string'
                ? payload.catalogId
                : '';
            const expanded = payload && payload.expanded === true;
            if (catalogId.length === 0) {
                throw new Error('office/documents: catalogId required for set_catalog_expanded');
            }
            const ids = new Set(Array.isArray(state.expandedCatalogIds) ? state.expandedCatalogIds : []);
            if (expanded) {
                ids.add(catalogId);
            } else {
                ids.delete(catalogId);
            }
            const expandedCatalogIds = [...ids];
            _writeStoredIds(EXPANDED_CATALOGS_STORAGE_KEY, expandedCatalogIds);
            return { ...state, expandedCatalogIds };
        }
        if (event.type === events.SET_FILTER_CATALOGS) {
            const ids = stringIds(payload === null ? undefined : payload.catalogIds);
            return { ...state, filterCatalogIds: ids };
        }
        if (event.type === events.CLEAR_FILTER) {
            return { ...state, filterCatalogIds: [], activeCatalogId: null, selectedCatalogId: null };
        }
        if (event.type === events.SET_VIEW_MODE) {
            const mode = payload && payload.viewMode;
            if (mode !== 'list' && mode !== 'grid') {
                throw new Error('office/documents: viewMode must be list|grid');
            }
            return { ...state, viewMode: mode };
        }
        if (event.type === events.SET_SEARCH_QUERY) {
            const q = payload && typeof payload.searchQuery === 'string'
                ? payload.searchQuery
                : '';
            return { ...state, searchQuery: q };
        }
        if (event.type === events.SET_SEARCH_MODE) {
            const searchMode = payload && payload.searchMode;
            if (searchMode !== 'files' && searchMode !== 'semantic') {
                throw new Error('office/documents: searchMode must be files|semantic');
            }
            storageSet(platformStorageKey('office', SEARCH_MODE_STORAGE_KEY), searchMode);
            return { ...state, searchMode };
        }
        if (event.type === events.SET_SORT) {
            const sortKey = payload && typeof payload.sortKey === 'string'
                ? payload.sortKey
                : state.sortKey;
            const sortDir = payload && (payload.sortDir === 'asc' || payload.sortDir === 'desc')
                ? payload.sortDir
                : state.sortDir;
            return { ...state, sortKey, sortDir };
        }
        if (event.type === events.SET_SELECTED_FILE) {
            const fileId = payload && typeof payload.fileId === 'string'
                ? payload.fileId
                : null;
            return {
                ...state,
                selectedFileId: fileId,
                selectedCatalogId: fileId ? null : state.selectedCatalogId,
            };
        }
        if (event.type === events.SET_SELECTED_CATALOG) {
            const catalogId = payload && typeof payload.catalogId === 'string'
                ? payload.catalogId
                : null;
            return {
                ...state,
                selectedCatalogId: catalogId,
                selectedFileId: catalogId ? null : state.selectedFileId,
            };
        }
        if (event.type === events.TOGGLE_FILE_SELECTION) {
            const fileId = payload && typeof payload.fileId === 'string'
                ? payload.fileId
                : '';
            if (fileId.length === 0) {
                throw new Error('office/documents: fileId required for toggle');
            }
            const selected = new Set(Array.isArray(state.selectedFileIds) ? state.selectedFileIds : []);
            if (selected.has(fileId)) {
                selected.delete(fileId);
            } else {
                selected.add(fileId);
            }
            return { ...state, selectedFileIds: [...selected] };
        }
        if (event.type === events.SET_FILE_SELECTION) {
            const ids = stringIds(payload === null ? undefined : payload.fileIds);
            return { ...state, selectedFileIds: ids };
        }
        if (event.type === events.CLEAR_FILE_SELECTION) {
            return { ...state, selectedFileIds: [], selectedFileId: null, selectedCatalogId: null };
        }
        if (event.type === events.UPLOAD_JOB_ADD) {
            const job: unknown = payload && payload.job;
            if (!isJsonObject(job) || typeof job.localId !== 'string') {
                throw new Error('office/documents: upload job.localId required');
            }
            const jobs = Array.isArray(docState.uploadJobs) ? docState.uploadJobs : [];
            return { ...state, uploadJobs: [...jobs, job] };
        }
        if (event.type === events.UPLOAD_JOB_UPDATE) {
            const localId = payload && typeof payload.localId === 'string'
                ? payload.localId
                : '';
            const patch = payload && payload.patch;
            if (localId.length === 0 || !isJsonObject(patch)) {
                throw new Error('office/documents: upload job update requires localId and patch');
            }
            const jobs = (Array.isArray(docState.uploadJobs) ? docState.uploadJobs : []).map((job) => {
                if (job.localId !== localId) {
                    return job;
                }
                return { ...job, ...patch };
            });
            return { ...state, uploadJobs: jobs };
        }
        if (event.type === events.UPLOAD_JOB_REMOVE) {
            const localId = payload && typeof payload.localId === 'string'
                ? payload.localId
                : '';
            const jobs = (Array.isArray(docState.uploadJobs) ? docState.uploadJobs : [])
                .filter((job) => job.localId !== localId);
            return { ...state, uploadJobs: jobs };
        }
        if (event.type === events.SET_EXPLORER_VIEW) {
            const explorerView = payload && payload.explorerView;
            if (
                explorerView !== 'catalog'
                && explorerView !== 'recent'
                && explorerView !== 'starred'
                && explorerView !== 'shared'
                && explorerView !== 'deleted'
            ) {
                throw new Error('office/documents: invalid explorerView');
            }
            storageSet(platformStorageKey('office', EXPLORER_VIEW_STORAGE_KEY), explorerView);
            return { ...state, explorerView, selectedCatalogId: null };
        }
        if (event.type === events.TOGGLE_STARRED) {
            const fileId = payload && typeof payload.fileId === 'string'
                ? payload.fileId
                : '';
            if (fileId.length === 0) {
                throw new Error('office/documents: fileId required for toggle starred');
            }
            const starred = new Set(Array.isArray(state.starredFileIds) ? state.starredFileIds : []);
            if (starred.has(fileId)) {
                starred.delete(fileId);
            } else {
                starred.add(fileId);
            }
            const starredFileIds = [...starred];
            _writeStoredIds(STARRED_STORAGE_KEY, starredFileIds);
            return { ...state, starredFileIds };
        }
        if (event.type === events.RECORD_RECENT_OPEN) {
            const fileId = payload && typeof payload.fileId === 'string'
                ? payload.fileId
                : '';
            if (fileId.length === 0) {
                throw new Error('office/documents: fileId required for recent');
            }
            const recent = [
                fileId,
                ...(Array.isArray(state.recentFileIds) ? state.recentFileIds : [])
                    .filter((id) => id !== fileId),
            ].slice(0, RECENT_LIMIT);
            _writeStoredIds(RECENT_STORAGE_KEY, recent);
            return { ...state, recentFileIds: recent };
        }
        return state;
    },
});

export const documentCreateEmptyOp = createAsyncOp({
    name: 'office/document_create_empty',
    successToastKey: 'documents:toast.document_created',
    errorToastKey: 'documents:toast.document_create_failed',
    transport: 'ws',
    wsTimeoutMs: 12_000,
    commandType: 'office/documents/empty_requested',
    restMirror: { method: 'POST', path: '/documents/api/v1/documents/empty' },
    onSuccess: (ctx, _result, event) => {
        _reloadVisibleDocuments(ctx, event);
    },
});

export const documentUploadOp = createAsyncOp({
    name: 'office/document_upload',
    successToastKey: 'documents:toast.document_uploaded',
    errorToastKey: 'documents:toast.document_upload_failed',
    restMirror: { method: 'POST', path: '/documents/api/v1/documents' },
    request: async ({ payload, ctx }) => {
        if (!isJsonObject(payload)) {
            throw new Error('office/document_upload: payload required');
        }
        const reqPayload = payload;
        if (!(reqPayload.file instanceof File) && !(reqPayload.file instanceof Blob)) {
            throw new Error('office/document_upload: payload.file (File|Blob) required');
        }
        if (typeof reqPayload.catalog_id !== 'string' || reqPayload.catalog_id.length === 0) {
            throw new Error('office/document_upload: payload.catalog_id required');
        }
        const nsHeaders = nsHeader(ctx);
        const namespaceId = nsHeaders['X-Platform-Namespace'];
        if (typeof namespaceId !== 'string' || namespaceId.length === 0) {
            throw new Error('office/document_upload: X-Platform-Namespace required');
        }
        const file =
            reqPayload.file instanceof File
                ? reqPayload.file
                : new File([reqPayload.file], 'document.bin', {
                    type: reqPayload.file.type.length > 0 ? reqPayload.file.type : 'application/octet-stream',
                });
        const uploaded = await uploadPlatformFile({
            file,
            spec: buildOfficeDocumentFileCreateSpecJson({
                namespaceId,
                catalogId: reqPayload.catalog_id,
            }),
            headers: nsHeaders,
        });
        if (typeof uploaded.file_id !== 'string' || uploaded.file_id.length === 0) {
            throw new Error('office/document_upload: upload result.file_id required');
        }
        const body: Record<string, unknown> = {
            file_id: uploaded.file_id,
            catalog_id: reqPayload.catalog_id,
        };
        if (typeof reqPayload.title === 'string' && reqPayload.title.length > 0) {
            body.title = reqPayload.title;
        }
        return httpRequest({
            method: 'POST',
            url: '/documents/api/v1/documents',
            body,
            headers: nsHeaders,
        });
    },
    onSuccess: (ctx, result, event) => {
        const eventPayload = isJsonObject(event.payload) ? event.payload : null;
        const localId = eventPayload && eventPayload.localId;
        if (typeof localId === 'string' && localId.length > 0) {
            ctx.dispatch(
                uploadJobEvent(documentsOp.events, 'UPLOAD_JOB_UPDATE'),
                { localId, patch: { status: 'done', progress: 100 } },
                { causation_id: event.id, source: 'local' },
            );
            window.setTimeout(() => {
                ctx.dispatch(
                    uploadJobEvent(documentsOp.events, 'UPLOAD_JOB_REMOVE'),
                    { localId },
                    { source: 'local' },
                );
            }, 3000);
        }
        const uploadResult = isJsonObject(result) ? result : null;
        if (uploadResult && typeof uploadResult.file_id === 'string') {
            if (eventPayload && eventPayload.openAfterUpload === true) {
                ctx.dispatch(
                    CoreEvents.ROUTER_NAVIGATE_REQUESTED,
                    { routeKey: 'document_editor', params: { fileId: uploadResult.file_id } },
                    { causation_id: event.id, source: 'local' },
                );
            }
        }
        const docState = officeDocuments(ctx.getState());
        if (!docState) {
            return;
        }
        ctx.dispatch(
            documentsOp.events.REQUESTED,
            buildDocumentsListPayload(docState, [eventPayload && eventPayload.catalog_id]),
            { causation_id: event.id, source: 'local' },
        );
    },
    onFailure: (ctx, _err, event) => {
        const eventPayload = isJsonObject(event.payload) ? event.payload : null;
        const localId = eventPayload && eventPayload.localId;
        if (typeof localId === 'string' && localId.length > 0) {
            ctx.dispatch(
                uploadJobEvent(documentsOp.events, 'UPLOAD_JOB_UPDATE'),
                { localId, patch: { status: 'failed', progress: 0 } },
                { causation_id: event.id, source: 'local' },
            );
        }
    },
});

export const documentRenameOp = createAsyncOp({
    name: 'office/document_rename',
    successToastKey: 'documents:toast.document_renamed',
    errorToastKey: 'documents:toast.document_rename_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'office/documents/rename_requested',
    restMirror: { method: 'PATCH', path: '/documents/api/v1/documents/:file_id' },
    onSuccess: (ctx, _result, event) => {
        _reloadVisibleDocuments(ctx, event);
    },
});

export const deletedDocumentsOp = createAsyncOp({
    name: 'office/documents_deleted',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'office/documents/deleted_list_requested',
    restMirror: { method: 'GET', path: '/documents/api/v1/documents/deleted' },
});

export const documentRestoreOp = createAsyncOp({
    name: 'office/document_restore',
    successToastKey: 'documents:toast.document_restored',
    errorToastKey: 'documents:toast.document_restore_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'office/documents/restore_requested',
    restMirror: { method: 'POST', path: '/documents/api/v1/documents/:file_id/restore' },
    onSuccess: (ctx, _result, event) => {
        ctx.dispatch(deletedDocumentsOp.events.REQUESTED, null, { causation_id: event.id, source: 'local' });
    },
});

export const documentPermanentDeleteOp = createAsyncOp({
    name: 'office/document_permanent_delete',
    successToastKey: 'documents:toast.document_permanent_deleted',
    errorToastKey: 'documents:toast.document_permanent_delete_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'office/documents/permanent_remove_requested',
    restMirror: { method: 'DELETE', path: '/documents/api/v1/documents/:file_id/permanent' },
    onSuccess: (ctx, _result, event) => {
        ctx.dispatch(deletedDocumentsOp.events.REQUESTED, null, { causation_id: event.id, source: 'local' });
    },
});

export const documentMoveOp = createAsyncOp({
    name: 'office/document_move',
    successToastKey: 'documents:toast.document_moved',
    errorToastKey: 'documents:toast.document_move_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'office/documents/move_requested',
    restMirror: { method: 'POST', path: '/documents/api/v1/documents/:file_id/move' },
    onSuccess: (ctx, _result, event) => {
        _reloadVisibleDocuments(ctx, event);
    },
});

export const documentShareCreateOp = createAsyncOp({
    name: 'office/document_share_create',
    successToastKey: 'documents:toast.share_created',
    errorToastKey: 'documents:toast.share_create_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'office/documents/share_create_requested',
    restMirror: { method: 'POST', path: '/documents/api/v1/documents/:file_id/shares' },
});

export const documentRemoveOp = createAsyncOp({
    name: 'office/document_remove',
    successToastKey: 'documents:toast.document_deleted',
    errorToastKey: 'documents:toast.document_delete_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'office/documents/remove_requested',
    restMirror: { method: 'DELETE', path: '/documents/api/v1/documents/:file_id' },
    onSuccess: (ctx, _result, event) => {
        _reloadVisibleDocuments(ctx, event);
    },
});

export const documentRenameForm = createForm({
    name: 'office/document_rename_form',
    schema: {
        file_id: { required: true },
        title: {
            required: true,
            minLength: 1,
            maxLength: 500,
            errorKey: 'form.document_title_required',
        },
    },
    initial: { file_id: '', title: '' },
    submitEvent: documentRenameOp.events.REQUESTED,
    buildPayload: (draft) => ({
        file_id: draft.file_id,
        title: typeof draft.title === 'string' ? draft.title.trim() : '',
    }),
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'office/documents': typeof documentsOp;
        'office/document_create_empty': typeof documentCreateEmptyOp;
        'office/document_upload': typeof documentUploadOp;
        'office/document_rename': typeof documentRenameOp;
        'office/documents_deleted': typeof deletedDocumentsOp;
        'office/document_restore': typeof documentRestoreOp;
        'office/document_permanent_delete': typeof documentPermanentDeleteOp;
        'office/document_move': typeof documentMoveOp;
        'office/document_share_create': typeof documentShareCreateOp;
        'office/document_remove': typeof documentRemoveOp;
        'office/document_rename_form': typeof documentRenameForm;
    }
}
