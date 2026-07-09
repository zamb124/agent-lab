/**
 * Office Catalog RAG — управление RAG-индексом каталога.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';
import {
    packAdvancedRetrievalPayload,
    packSearchRequestOptions,
} from '@platform/lib/rag/pack_search_request_options.js';
import { nsHeader } from './_namespace-header.js';

function _catalogIdFromPayload(payload, opName) {
    if (!payload || typeof payload.catalogId !== 'string' || payload.catalogId.length === 0) {
        throw new Error(`${opName}: payload.catalogId required`);
    }
    return payload.catalogId;
}

function _settingsPatchBody(payload) {
    /** @type {Record<string, unknown>} */
    const body = {
        ...packSearchRequestOptions(payload),
        ...packAdvancedRetrievalPayload(payload),
    };
    if (payload && typeof payload.includeSubcatalogs === 'boolean') {
        body.include_subcatalogs = payload.includeSubcatalogs;
    }
    if (payload && payload.clearSearchOptions === true) {
        body.clear_search_options = true;
    }
    if (Object.keys(body).length === 0) {
        throw new Error('office/catalog_rag_settings: patch body must not be empty');
    }
    return body;
}

export const catalogRagStatusOp = createAsyncOp({
    name: 'office/catalog_rag_status',
    silent: true,
    restMirror: { method: 'GET', path: '/documents/api/v1/catalogs/:catalog_id/rag-index/status' },
    request: ({ payload, ctx }) => {
        const catalogId = _catalogIdFromPayload(payload, 'office/catalog_rag_status');
        return httpRequest({
            method: 'GET',
            url: `/documents/api/v1/catalogs/${encodeURIComponent(catalogId)}/rag-index/status`,
            headers: nsHeader(ctx),
        });
    },
});

export const catalogRagEnableOp = createAsyncOp({
    name: 'office/catalog_rag_enable',
    successToastKey: 'documents:toast.catalog_rag_enabled',
    errorToastKey: 'documents:toast.catalog_rag_enable_failed',
    restMirror: { method: 'POST', path: '/documents/api/v1/catalogs/:catalog_id/rag-index/enable' },
    request: ({ payload, ctx }) => {
        const catalogId = _catalogIdFromPayload(payload, 'office/catalog_rag_enable');
        return httpRequest({
            method: 'POST',
            url: `/documents/api/v1/catalogs/${encodeURIComponent(catalogId)}/rag-index/enable`,
            headers: nsHeader(ctx),
        });
    },
    onSuccess: (ctx, _result, event) => {
        ctx.dispatch(
            catalogRagStatusOp.events.REQUESTED,
            { catalogId: event.payload.catalogId },
            { causation_id: event.id, source: 'local' },
        );
    },
});

export const catalogRagDisableOp = createAsyncOp({
    name: 'office/catalog_rag_disable',
    successToastKey: 'documents:toast.catalog_rag_disabled',
    errorToastKey: 'documents:toast.catalog_rag_disable_failed',
    restMirror: { method: 'POST', path: '/documents/api/v1/catalogs/:catalog_id/rag-index/disable' },
    request: ({ payload, ctx }) => {
        const catalogId = _catalogIdFromPayload(payload, 'office/catalog_rag_disable');
        return httpRequest({
            method: 'POST',
            url: `/documents/api/v1/catalogs/${encodeURIComponent(catalogId)}/rag-index/disable`,
            headers: nsHeader(ctx),
        });
    },
    onSuccess: (ctx, _result, event) => {
        ctx.dispatch(
            catalogRagStatusOp.events.REQUESTED,
            { catalogId: event.payload.catalogId },
            { causation_id: event.id, source: 'local' },
        );
    },
});

export const catalogRagRebuildOp = createAsyncOp({
    name: 'office/catalog_rag_rebuild',
    successToastKey: 'documents:toast.catalog_rag_rebuild_started',
    errorToastKey: 'documents:toast.catalog_rag_rebuild_failed',
    restMirror: { method: 'POST', path: '/documents/api/v1/catalogs/:catalog_id/rag-index/rebuild' },
    request: ({ payload, ctx }) => {
        const catalogId = _catalogIdFromPayload(payload, 'office/catalog_rag_rebuild');
        return httpRequest({
            method: 'POST',
            url: `/documents/api/v1/catalogs/${encodeURIComponent(catalogId)}/rag-index/rebuild`,
            headers: nsHeader(ctx),
        });
    },
    onSuccess: (ctx, _result, event) => {
        ctx.dispatch(
            catalogRagStatusOp.events.REQUESTED,
            { catalogId: event.payload.catalogId },
            { causation_id: event.id, source: 'local' },
        );
    },
});

export const catalogRagSettingsOp = createAsyncOp({
    name: 'office/catalog_rag_settings',
    successToastKey: 'documents:toast.catalog_rag_settings_saved',
    errorToastKey: 'documents:toast.catalog_rag_settings_failed',
    restMirror: {
        method: 'PATCH',
        path: '/documents/api/v1/catalogs/:catalog_id/rag-index/settings',
    },
    request: ({ payload, ctx }) => {
        const catalogId = _catalogIdFromPayload(payload, 'office/catalog_rag_settings');
        return httpRequest({
            method: 'PATCH',
            url: `/documents/api/v1/catalogs/${encodeURIComponent(catalogId)}/rag-index/settings`,
            headers: nsHeader(ctx),
            body: _settingsPatchBody(payload),
        });
    },
    onSuccess: (ctx, _result, event) => {
        ctx.dispatch(
            catalogRagStatusOp.events.REQUESTED,
            { catalogId: event.payload.catalogId },
            { causation_id: event.id, source: 'local' },
        );
    },
});
