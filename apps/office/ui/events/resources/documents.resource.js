/**
 * Office Documents — привязки документов OnlyOffice к каталогам.
 *
 * Backend (`/documents/api/v1/documents` + nested):
 *   GET    /documents?catalog_ids=...        → OfficeDocumentListResponse { items }
 *   POST   /documents                        → OfficeDocumentCreateResponse (multipart: file, title?, catalog_id)
 *   POST   /documents/empty                  → OfficeDocumentCreateResponse (JSON: title, document_type, catalog_id, spreadsheet_format?)
 *   PATCH  /documents/{binding_id}           → OfficeDocumentRenameResponse (JSON: title)
 *   DELETE /documents/{binding_id}           → 204
 *
 * `documentsOp` — list по `catalogIds` (sub-resource), slice хранит
 * `items` + `loadedCatalogIds` + `activeCatalogId` + `filterCatalogIds`.
 * `activeCatalogId` — последний выбранный каталог (для создания/загрузки
 * без явного выбора), `filterCatalogIds` — мультивыбор фильтра в списке.
 *
 * `documentRenameForm` — форма для модалки `office.document_rename`,
 * submitEvent → `documentRenameOp.events.REQUESTED`.
 */

import { createAsyncOp, createForm } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { platformStorageKey } from '@platform/lib/utils/storage-keys.js';
import { nsHeader } from './_namespace-header.js';

const RECENT_STORAGE_KEY = 'documents_explorer_recent_ids';
const STARRED_STORAGE_KEY = 'documents_explorer_starred_ids';
const EXPLORER_VIEW_STORAGE_KEY = 'documents_explorer_view';
const EXPANDED_CATALOGS_STORAGE_KEY = 'documents_explorer_expanded_catalog_ids';
const SEARCH_MODE_STORAGE_KEY = 'documents_explorer_search_mode';
const RECENT_LIMIT = 20;

function _readStoredSearchMode() {
    const raw = window.localStorage.getItem(platformStorageKey('office', SEARCH_MODE_STORAGE_KEY));
    if (raw === 'files' || raw === 'semantic') {
        return raw;
    }
    return 'files';
}

function _readStoredIds(storageKey) {
    const raw = window.localStorage.getItem(platformStorageKey('office', storageKey));
    if (typeof raw !== 'string' || raw.length === 0) {
        return [];
    }
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
        throw new Error(`documents: invalid stored ids for ${storageKey}`);
    }
    return parsed.filter((id) => typeof id === 'string' && id.length > 0);
}

function _writeStoredIds(storageKey, ids) {
    window.localStorage.setItem(platformStorageKey('office', storageKey), JSON.stringify(ids));
}

function _normalizeCatalogIds(raw) {
    if (!Array.isArray(raw)) {
        throw new Error('documents: payload.catalogIds (array) required');
    }
    const ids = [];
    const seen = new Set();
    for (const id of raw) {
        const v = typeof id === 'string' ? id.trim() : '';
        if (v.length === 0) continue;
        if (seen.has(v)) continue;
        seen.add(v);
        ids.push(v);
    }
    if (ids.length === 0) {
        throw new Error('documents: payload.catalogIds must contain at least one non-empty id');
    }
    return ids;
}

function _buildDocumentsQuery(ids, payload) {
    const parts = ids.map((id) => `catalog_ids=${encodeURIComponent(id)}`);
    if (payload && typeof payload.q === 'string' && payload.q.trim().length > 0) {
        parts.push(`q=${encodeURIComponent(payload.q.trim())}`);
    }
    const sortKey = payload && typeof payload.sortKey === 'string' ? payload.sortKey : '';
    const sortDir = payload && typeof payload.sortDir === 'string' ? payload.sortDir : '';
    if (sortKey.length > 0) {
        parts.push(`sort=${encodeURIComponent(sortKey)}`);
    }
    if (sortDir === 'asc' || sortDir === 'desc') {
        parts.push(`order=${encodeURIComponent(sortDir)}`);
    }
    return parts.join('&');
}

export function buildDocumentsListPayload(docState, catalogIds) {
    const ids = _normalizeCatalogIds(catalogIds);
    return {
        catalogIds: ids,
        q: docState.searchQuery,
        sortKey: docState.sortKey,
        sortDir: docState.sortDir,
    };
}

export const documentsOp = createAsyncOp({
    name: 'office/documents',
    silent: true,
    restMirror: { method: 'GET', path: '/documents/api/v1/documents' },
    request: ({ payload, ctx }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('office/documents: payload required');
        }
        const ids = _normalizeCatalogIds(payload.catalogIds);
        const qs = _buildDocumentsQuery(ids, payload);
        return httpRequest({
            method: 'GET',
            url: `/documents/api/v1/documents?${qs}`,
            headers: nsHeader(ctx),
        });
    },
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
        selectedBindingId: null,
        selectedBindingIds: [],
        uploadJobs: [],
        explorerView: 'catalog',
        recentBindingIds: _readStoredIds(RECENT_STORAGE_KEY),
        starredBindingIds: _readStoredIds(STARRED_STORAGE_KEY),
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
        SET_SELECTED_BINDING: 'set_selected_binding',
        TOGGLE_BINDING_SELECTION: 'toggle_binding_selection',
        SET_BINDING_SELECTION: 'set_binding_selection',
        CLEAR_BINDING_SELECTION: 'clear_binding_selection',
        UPLOAD_JOB_ADD:      'upload_job_add',
        UPLOAD_JOB_UPDATE:   'upload_job_update',
        UPLOAD_JOB_REMOVE:   'upload_job_remove',
        SET_EXPLORER_VIEW:   'set_explorer_view',
        TOGGLE_STARRED:      'toggle_starred',
        RECORD_RECENT_OPEN:  'record_recent_open',
    },
    actions: {
        setActiveCatalog:  'set_active_catalog',
        setCatalogExpanded: 'set_catalog_expanded',
        setFilterCatalogs: 'set_filter_catalogs',
        clearFilter:       'clear_filter',
        setViewMode:       'set_view_mode',
        setSearchQuery:    'set_search_query',
        setSearchMode:     'set_search_mode',
        setSort:           'set_sort',
        setSelectedBinding: 'set_selected_binding',
        toggleBindingSelection: 'toggle_binding_selection',
        setBindingSelection: 'set_binding_selection',
        clearBindingSelection: 'clear_binding_selection',
        setExplorerView: 'set_explorer_view',
        toggleStarred: 'toggle_starred',
        recordRecentOpen: 'record_recent_open',
    },
    extraReducer: (state, event, events) => {
        if (event.type === events.REQUESTED) {
            const ids = _normalizeCatalogIds(event.payload.catalogIds);
            return { ...state, items: [], loadedCatalogIds: ids };
        }
        if (event.type === events.SUCCEEDED) {
            const result = event.payload.result;
            if (!result || !Array.isArray(result.items)) {
                throw new Error('office/documents: SUCCEEDED.result.items required (array)');
            }
            return { ...state, items: result.items };
        }
        if (event.type === events.SET_ACTIVE_CATALOG) {
            const catalogId = event.payload && typeof event.payload.catalogId === 'string'
                ? event.payload.catalogId
                : null;
            return {
                ...state,
                activeCatalogId: catalogId,
            };
        }
        if (event.type === events.SET_CATALOG_EXPANDED) {
            const catalogId = event.payload && typeof event.payload.catalogId === 'string'
                ? event.payload.catalogId
                : '';
            const expanded = event.payload && event.payload.expanded === true;
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
            const ids = Array.isArray(event.payload && event.payload.catalogIds)
                ? event.payload.catalogIds.filter((x) => typeof x === 'string' && x.length > 0)
                : [];
            return { ...state, filterCatalogIds: ids };
        }
        if (event.type === events.CLEAR_FILTER) {
            return { ...state, filterCatalogIds: [], activeCatalogId: null };
        }
        if (event.type === events.SET_VIEW_MODE) {
            const mode = event.payload && event.payload.viewMode;
            if (mode !== 'list' && mode !== 'grid') {
                throw new Error('office/documents: viewMode must be list|grid');
            }
            return { ...state, viewMode: mode };
        }
        if (event.type === events.SET_SEARCH_QUERY) {
            const q = event.payload && typeof event.payload.searchQuery === 'string'
                ? event.payload.searchQuery
                : '';
            return { ...state, searchQuery: q };
        }
        if (event.type === events.SET_SEARCH_MODE) {
            const searchMode = event.payload && event.payload.searchMode;
            if (searchMode !== 'files' && searchMode !== 'semantic') {
                throw new Error('office/documents: searchMode must be files|semantic');
            }
            window.localStorage.setItem(
                platformStorageKey('office', SEARCH_MODE_STORAGE_KEY),
                searchMode,
            );
            return { ...state, searchMode };
        }
        if (event.type === events.SET_SORT) {
            const sortKey = event.payload && typeof event.payload.sortKey === 'string'
                ? event.payload.sortKey
                : state.sortKey;
            const sortDir = event.payload && (event.payload.sortDir === 'asc' || event.payload.sortDir === 'desc')
                ? event.payload.sortDir
                : state.sortDir;
            return { ...state, sortKey, sortDir };
        }
        if (event.type === events.SET_SELECTED_BINDING) {
            const bindingId = event.payload && typeof event.payload.bindingId === 'string'
                ? event.payload.bindingId
                : null;
            return { ...state, selectedBindingId: bindingId };
        }
        if (event.type === events.TOGGLE_BINDING_SELECTION) {
            const bindingId = event.payload && typeof event.payload.bindingId === 'string'
                ? event.payload.bindingId
                : '';
            if (bindingId.length === 0) {
                throw new Error('office/documents: bindingId required for toggle');
            }
            const selected = new Set(Array.isArray(state.selectedBindingIds) ? state.selectedBindingIds : []);
            if (selected.has(bindingId)) {
                selected.delete(bindingId);
            } else {
                selected.add(bindingId);
            }
            return { ...state, selectedBindingIds: [...selected] };
        }
        if (event.type === events.SET_BINDING_SELECTION) {
            const ids = Array.isArray(event.payload && event.payload.bindingIds)
                ? event.payload.bindingIds.filter((x) => typeof x === 'string' && x.length > 0)
                : [];
            return { ...state, selectedBindingIds: ids };
        }
        if (event.type === events.CLEAR_BINDING_SELECTION) {
            return { ...state, selectedBindingIds: [], selectedBindingId: null };
        }
        if (event.type === events.UPLOAD_JOB_ADD) {
            const job = event.payload && event.payload.job;
            if (!job || typeof job.localId !== 'string') {
                throw new Error('office/documents: upload job.localId required');
            }
            const jobs = Array.isArray(state.uploadJobs) ? state.uploadJobs : [];
            return { ...state, uploadJobs: [...jobs, job] };
        }
        if (event.type === events.UPLOAD_JOB_UPDATE) {
            const localId = event.payload && typeof event.payload.localId === 'string'
                ? event.payload.localId
                : '';
            const patch = event.payload && event.payload.patch;
            if (localId.length === 0 || !patch || typeof patch !== 'object') {
                throw new Error('office/documents: upload job update requires localId and patch');
            }
            const jobs = (Array.isArray(state.uploadJobs) ? state.uploadJobs : []).map((job) => {
                if (job.localId !== localId) {
                    return job;
                }
                return { ...job, ...patch };
            });
            return { ...state, uploadJobs: jobs };
        }
        if (event.type === events.UPLOAD_JOB_REMOVE) {
            const localId = event.payload && typeof event.payload.localId === 'string'
                ? event.payload.localId
                : '';
            const jobs = (Array.isArray(state.uploadJobs) ? state.uploadJobs : [])
                .filter((job) => job.localId !== localId);
            return { ...state, uploadJobs: jobs };
        }
        if (event.type === events.SET_EXPLORER_VIEW) {
            const explorerView = event.payload && event.payload.explorerView;
            if (
                explorerView !== 'catalog'
                && explorerView !== 'recent'
                && explorerView !== 'starred'
                && explorerView !== 'shared'
                && explorerView !== 'deleted'
            ) {
                throw new Error('office/documents: invalid explorerView');
            }
            window.localStorage.setItem(
                platformStorageKey('office', EXPLORER_VIEW_STORAGE_KEY),
                explorerView,
            );
            return { ...state, explorerView };
        }
        if (event.type === events.TOGGLE_STARRED) {
            const bindingId = event.payload && typeof event.payload.bindingId === 'string'
                ? event.payload.bindingId
                : '';
            if (bindingId.length === 0) {
                throw new Error('office/documents: bindingId required for toggle starred');
            }
            const starred = new Set(Array.isArray(state.starredBindingIds) ? state.starredBindingIds : []);
            if (starred.has(bindingId)) {
                starred.delete(bindingId);
            } else {
                starred.add(bindingId);
            }
            const starredBindingIds = [...starred];
            _writeStoredIds(STARRED_STORAGE_KEY, starredBindingIds);
            return { ...state, starredBindingIds };
        }
        if (event.type === events.RECORD_RECENT_OPEN) {
            const bindingId = event.payload && typeof event.payload.bindingId === 'string'
                ? event.payload.bindingId
                : '';
            if (bindingId.length === 0) {
                throw new Error('office/documents: bindingId required for recent');
            }
            const recent = [
                bindingId,
                ...(Array.isArray(state.recentBindingIds) ? state.recentBindingIds : [])
                    .filter((id) => id !== bindingId),
            ].slice(0, RECENT_LIMIT);
            _writeStoredIds(RECENT_STORAGE_KEY, recent);
            return { ...state, recentBindingIds: recent };
        }
        return state;
    },
});

export const documentCreateEmptyOp = createAsyncOp({
    name: 'office/document_create_empty',
    successToastKey: 'documents:toast.document_created',
    errorToastKey: 'documents:toast.document_create_failed',
    restMirror: { method: 'POST', path: '/documents/api/v1/documents/empty' },
    request: ({ payload, ctx }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('office/document_create_empty: payload required');
        }
        if (typeof payload.title !== 'string' || payload.title.length === 0) {
            throw new Error('office/document_create_empty: payload.title required');
        }
        if (typeof payload.documentType !== 'string') {
            throw new Error('office/document_create_empty: payload.documentType required');
        }
        if (typeof payload.catalogId !== 'string' || payload.catalogId.length === 0) {
            throw new Error('office/document_create_empty: payload.catalogId required');
        }
        const body = {
            title: payload.title,
            document_type: payload.documentType,
            catalog_id: payload.catalogId,
        };
        if (payload.documentType === 'cell' && typeof payload.spreadsheetFormat === 'string') {
            body.spreadsheet_format = payload.spreadsheetFormat;
        }
        return httpRequest({
            method: 'POST',
            url: '/documents/api/v1/documents/empty',
            body,
            headers: nsHeader(ctx),
        });
    },
    onSuccess: (ctx, result, event) => {
        if (result && typeof result.binding_id === 'string') {
            if (event.payload.openAfterCreate === true) {
                ctx.dispatch(
                    CoreEvents.ROUTER_NAVIGATE_REQUESTED,
                    { routeKey: 'document_editor', params: { bindingId: result.binding_id } },
                    { causation_id: event.id, source: 'local' },
                );
            }
        }
        const docState = ctx.getState().officeDocuments;
        ctx.dispatch(
            documentsOp.events.REQUESTED,
            buildDocumentsListPayload(docState, [event.payload.catalogId]),
            { causation_id: event.id, source: 'local' },
        );
    },
});

export const documentUploadOp = createAsyncOp({
    name: 'office/document_upload',
    successToastKey: 'documents:toast.document_uploaded',
    errorToastKey: 'documents:toast.document_upload_failed',
    restMirror: { method: 'POST', path: '/documents/api/v1/documents' },
    request: ({ payload, ctx }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('office/document_upload: payload required');
        }
        if (!(payload.file instanceof File) && !(payload.file instanceof Blob)) {
            throw new Error('office/document_upload: payload.file (File|Blob) required');
        }
        if (typeof payload.catalogId !== 'string' || payload.catalogId.length === 0) {
            throw new Error('office/document_upload: payload.catalogId required');
        }
        const fd = new FormData();
        fd.append('file', payload.file);
        if (typeof payload.title === 'string' && payload.title.length > 0) {
            fd.append('title', payload.title);
        }
        fd.append('catalog_id', payload.catalogId);
        return httpRequest({
            method: 'POST',
            url: '/documents/api/v1/documents',
            body: fd,
            headers: nsHeader(ctx),
        });
    },
    onSuccess: (ctx, result, event) => {
        const localId = event.payload.localId;
        if (typeof localId === 'string' && localId.length > 0) {
            ctx.dispatch(
                documentsOp.events.UPLOAD_JOB_UPDATE,
                { localId, patch: { status: 'done', progress: 100 } },
                { causation_id: event.id, source: 'local' },
            );
            window.setTimeout(() => {
                ctx.dispatch(
                    documentsOp.events.UPLOAD_JOB_REMOVE,
                    { localId },
                    { source: 'local' },
                );
            }, 3000);
        }
        if (result && typeof result.binding_id === 'string') {
            if (event.payload.openAfterUpload === true) {
                ctx.dispatch(
                    CoreEvents.ROUTER_NAVIGATE_REQUESTED,
                    { routeKey: 'document_editor', params: { bindingId: result.binding_id } },
                    { causation_id: event.id, source: 'local' },
                );
            }
        }
        const docState = ctx.getState().officeDocuments;
        ctx.dispatch(
            documentsOp.events.REQUESTED,
            buildDocumentsListPayload(docState, [event.payload.catalogId]),
            { causation_id: event.id, source: 'local' },
        );
    },
    onFailure: (ctx, _err, event) => {
        const localId = event.payload.localId;
        if (typeof localId === 'string' && localId.length > 0) {
            ctx.dispatch(
                documentsOp.events.UPLOAD_JOB_UPDATE,
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
    restMirror: { method: 'PATCH', path: '/documents/api/v1/documents/:binding_id' },
    request: ({ payload, ctx }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('office/document_rename: payload required');
        }
        if (typeof payload.bindingId !== 'string' || payload.bindingId.length === 0) {
            throw new Error('office/document_rename: payload.bindingId required');
        }
        if (typeof payload.title !== 'string' || payload.title.length === 0) {
            throw new Error('office/document_rename: payload.title required');
        }
        return httpRequest({
            method: 'PATCH',
            url: `/documents/api/v1/documents/${encodeURIComponent(payload.bindingId)}`,
            body: { title: payload.title },
            headers: nsHeader(ctx),
        });
    },
    onSuccess: (ctx, _result, event) => {
        const docState = ctx.getState().officeDocuments;
        if (Array.isArray(event.payload.catalogIds) && event.payload.catalogIds.length > 0) {
            ctx.dispatch(
                documentsOp.events.REQUESTED,
                buildDocumentsListPayload(docState, event.payload.catalogIds),
                { causation_id: event.id, source: 'local' },
            );
        }
    },
});

export const deletedDocumentsOp = createAsyncOp({
    name: 'office/documents_deleted',
    silent: true,
    restMirror: { method: 'GET', path: '/documents/api/v1/documents/deleted' },
    request: ({ ctx }) => httpRequest({
        method: 'GET',
        url: '/documents/api/v1/documents/deleted',
        headers: nsHeader(ctx),
    }),
});

export const documentRestoreOp = createAsyncOp({
    name: 'office/document_restore',
    successToastKey: 'documents:toast.document_restored',
    errorToastKey: 'documents:toast.document_restore_failed',
    restMirror: { method: 'POST', path: '/documents/api/v1/documents/:binding_id/restore' },
    request: ({ payload, ctx }) => {
        if (!payload || typeof payload.bindingId !== 'string' || payload.bindingId.length === 0) {
            throw new Error('office/document_restore: payload.bindingId required');
        }
        return httpRequest({
            method: 'POST',
            url: `/documents/api/v1/documents/${encodeURIComponent(payload.bindingId)}/restore`,
            headers: nsHeader(ctx),
        });
    },
    onSuccess: (ctx, _result, event) => {
        ctx.dispatch(deletedDocumentsOp.events.REQUESTED, null, { causation_id: event.id, source: 'local' });
    },
});

export const documentPermanentDeleteOp = createAsyncOp({
    name: 'office/document_permanent_delete',
    successToastKey: 'documents:toast.document_permanent_deleted',
    errorToastKey: 'documents:toast.document_permanent_delete_failed',
    restMirror: { method: 'DELETE', path: '/documents/api/v1/documents/:binding_id/permanent' },
    request: ({ payload, ctx }) => {
        if (!payload || typeof payload.bindingId !== 'string' || payload.bindingId.length === 0) {
            throw new Error('office/document_permanent_delete: payload.bindingId required');
        }
        return httpRequest({
            method: 'DELETE',
            url: `/documents/api/v1/documents/${encodeURIComponent(payload.bindingId)}/permanent`,
            headers: nsHeader(ctx),
        });
    },
    onSuccess: (ctx, _result, event) => {
        ctx.dispatch(deletedDocumentsOp.events.REQUESTED, null, { causation_id: event.id, source: 'local' });
    },
});

export const documentMoveOp = createAsyncOp({
    name: 'office/document_move',
    successToastKey: 'documents:toast.document_moved',
    errorToastKey: 'documents:toast.document_move_failed',
    restMirror: { method: 'POST', path: '/documents/api/v1/documents/:binding_id/move' },
    request: ({ payload, ctx }) => {
        if (!payload || typeof payload.bindingId !== 'string' || payload.bindingId.length === 0) {
            throw new Error('office/document_move: payload.bindingId required');
        }
        if (typeof payload.catalogId !== 'string' || payload.catalogId.length === 0) {
            throw new Error('office/document_move: payload.catalogId required');
        }
        return httpRequest({
            method: 'POST',
            url: `/documents/api/v1/documents/${encodeURIComponent(payload.bindingId)}/move`,
            body: { catalog_id: payload.catalogId },
            headers: nsHeader(ctx),
        });
    },
    onSuccess: (ctx, _result, event) => {
        const docState = ctx.getState().officeDocuments;
        const targetCatalogId = event.payload.catalogId;
        const reloadCatalogId = typeof docState.activeCatalogId === 'string' && docState.activeCatalogId.length > 0
            ? docState.activeCatalogId
            : targetCatalogId;
        ctx.dispatch(
            documentsOp.events.REQUESTED,
            buildDocumentsListPayload(docState, [reloadCatalogId]),
            { causation_id: event.id, source: 'local' },
        );
    },
});

export const documentShareCreateOp = createAsyncOp({
    name: 'office/document_share_create',
    successToastKey: 'documents:toast.share_created',
    errorToastKey: 'documents:toast.share_create_failed',
    restMirror: { method: 'POST', path: '/documents/api/v1/documents/:binding_id/shares' },
    request: ({ payload, ctx }) => {
        if (!payload || typeof payload.bindingId !== 'string' || payload.bindingId.length === 0) {
            throw new Error('office/document_share_create: payload.bindingId required');
        }
        const permission = payload.permission === 'edit' ? 'edit' : 'view';
        const expiresInHours = typeof payload.expiresInHours === 'number' ? payload.expiresInHours : null;
        return httpRequest({
            method: 'POST',
            url: `/documents/api/v1/documents/${encodeURIComponent(payload.bindingId)}/shares`,
            body: { permission, expires_in_hours: expiresInHours },
            headers: nsHeader(ctx),
        });
    },
});

export const documentRemoveOp = createAsyncOp({
    name: 'office/document_remove',
    successToastKey: 'documents:toast.document_deleted',
    errorToastKey: 'documents:toast.document_delete_failed',
    restMirror: { method: 'DELETE', path: '/documents/api/v1/documents/:binding_id' },
    request: ({ payload, ctx }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('office/document_remove: payload required');
        }
        if (typeof payload.bindingId !== 'string' || payload.bindingId.length === 0) {
            throw new Error('office/document_remove: payload.bindingId required');
        }
        return httpRequest({
            method: 'DELETE',
            url: `/documents/api/v1/documents/${encodeURIComponent(payload.bindingId)}`,
            headers: nsHeader(ctx),
        });
    },
    onSuccess: (ctx, _result, event) => {
        const docState = ctx.getState().officeDocuments;
        if (Array.isArray(event.payload.catalogIds) && event.payload.catalogIds.length > 0) {
            ctx.dispatch(
                documentsOp.events.REQUESTED,
                buildDocumentsListPayload(docState, event.payload.catalogIds),
                { causation_id: event.id, source: 'local' },
            );
        }
    },
});

export const documentRenameForm = createForm({
    name: 'office/document_rename_form',
    schema: {
        binding_id: { required: true },
        title: {
            required: true,
            minLength: 1,
            maxLength: 500,
            errorKey: 'form.document_title_required',
        },
        catalog_ids: {},
    },
    initial: { binding_id: '', title: '', catalog_ids: [] },
    submitEvent: documentRenameOp.events.REQUESTED,
    buildPayload: (draft) => ({
        bindingId: draft.binding_id,
        title: typeof draft.title === 'string' ? draft.title.trim() : '',
        catalogIds: Array.isArray(draft.catalog_ids) ? draft.catalog_ids : [],
    }),
});
