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
import { nsHeader } from './_namespace-header.js';

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

export const documentsOp = createAsyncOp({
    name: 'office/documents',
    silent: true,
    restMirror: { method: 'GET', path: '/documents/api/v1/documents' },
    request: ({ payload, ctx }) => {
        if (!payload || typeof payload !== 'object') {
            throw new Error('office/documents: payload required');
        }
        const ids = _normalizeCatalogIds(payload.catalogIds);
        const qs = ids.map((id) => `catalog_ids=${encodeURIComponent(id)}`).join('&');
        return httpRequest({
            method: 'GET',
            url: `/documents/api/v1/documents?${qs}`,
            headers: nsHeader(ctx),
        });
    },
    extraInitial: { items: [], loadedCatalogIds: [], activeCatalogId: null, filterCatalogIds: [] },
    extraEvents: {
        SET_ACTIVE_CATALOG:  'set_active_catalog',
        SET_FILTER_CATALOGS: 'set_filter_catalogs',
        CLEAR_FILTER:        'clear_filter',
    },
    actions: {
        setActiveCatalog:  'set_active_catalog',
        setFilterCatalogs: 'set_filter_catalogs',
        clearFilter:       'clear_filter',
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
            return { ...state, activeCatalogId: catalogId };
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
        ctx.dispatch(
            documentsOp.events.REQUESTED,
            { catalogIds: [event.payload.catalogId] },
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
        if (result && typeof result.binding_id === 'string') {
            if (event.payload.openAfterUpload === true) {
                ctx.dispatch(
                    CoreEvents.ROUTER_NAVIGATE_REQUESTED,
                    { routeKey: 'document_editor', params: { bindingId: result.binding_id } },
                    { causation_id: event.id, source: 'local' },
                );
            }
        }
        ctx.dispatch(
            documentsOp.events.REQUESTED,
            { catalogIds: [event.payload.catalogId] },
            { causation_id: event.id, source: 'local' },
        );
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
        if (Array.isArray(event.payload.catalogIds) && event.payload.catalogIds.length > 0) {
            ctx.dispatch(
                documentsOp.events.REQUESTED,
                { catalogIds: event.payload.catalogIds },
                { causation_id: event.id, source: 'local' },
            );
        }
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
        if (Array.isArray(event.payload.catalogIds) && event.payload.catalogIds.length > 0) {
            ctx.dispatch(
                documentsOp.events.REQUESTED,
                { catalogIds: event.payload.catalogIds },
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
