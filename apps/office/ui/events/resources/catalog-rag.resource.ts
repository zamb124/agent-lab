/**
 * Office Catalog RAG — управление RAG-индексом каталога.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import type { PlatformEvent } from '@platform/lib/events/contract.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

function catalogIdOf(payload: unknown, label: string): string {
    if (!isPlainRecord(payload)) {
        throw new Error(`${label}: payload.catalog_id required`);
    }
    const catalogId = payload.catalog_id;
    if (typeof catalogId !== 'string' || catalogId.length === 0) {
        throw new Error(`${label}: payload.catalog_id required`);
    }
    return catalogId;
}

export const catalogRagStatusOp = createAsyncOp({
    name: 'office/catalog_rag_status',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'office/catalogs/rag_status_requested',
    restMirror: { method: 'GET', path: '/documents/api/v1/catalogs/:catalog_id/rag-index/status' },
});

export const catalogRagEnableOp = createAsyncOp({
    name: 'office/catalog_rag_enable',
    successToastKey: 'documents:toast.catalog_rag_enabled',
    errorToastKey: 'documents:toast.catalog_rag_enable_failed',
    transport: 'ws',
    wsTimeoutMs: 12_000,
    commandType: 'office/catalogs/rag_enable_requested',
    restMirror: { method: 'POST', path: '/documents/api/v1/catalogs/:catalog_id/rag-index/enable' },
    onSuccess: (ctx, _result, event: PlatformEvent) => {
        const catalogId = catalogIdOf(event.payload, 'office/catalog_rag_enable');
        ctx.dispatch(
            catalogRagStatusOp.events.REQUESTED,
            { catalog_id: catalogId },
            { causation_id: event.id, source: 'local' },
        );
    },
});

export const catalogRagDisableOp = createAsyncOp({
    name: 'office/catalog_rag_disable',
    successToastKey: 'documents:toast.catalog_rag_disabled',
    errorToastKey: 'documents:toast.catalog_rag_disable_failed',
    transport: 'ws',
    wsTimeoutMs: 12_000,
    commandType: 'office/catalogs/rag_disable_requested',
    restMirror: { method: 'POST', path: '/documents/api/v1/catalogs/:catalog_id/rag-index/disable' },
    onSuccess: (ctx, _result, event: PlatformEvent) => {
        const catalogId = catalogIdOf(event.payload, 'office/catalog_rag_disable');
        ctx.dispatch(
            catalogRagStatusOp.events.REQUESTED,
            { catalog_id: catalogId },
            { causation_id: event.id, source: 'local' },
        );
    },
});

export const catalogRagRebuildOp = createAsyncOp({
    name: 'office/catalog_rag_rebuild',
    successToastKey: 'documents:toast.catalog_rag_rebuild_started',
    errorToastKey: 'documents:toast.catalog_rag_rebuild_failed',
    transport: 'ws',
    wsTimeoutMs: 12_000,
    commandType: 'office/catalogs/rag_rebuild_requested',
    restMirror: { method: 'POST', path: '/documents/api/v1/catalogs/:catalog_id/rag-index/rebuild' },
    onSuccess: (ctx, _result, event: PlatformEvent) => {
        const catalogId = catalogIdOf(event.payload, 'office/catalog_rag_rebuild');
        ctx.dispatch(
            catalogRagStatusOp.events.REQUESTED,
            { catalog_id: catalogId },
            { causation_id: event.id, source: 'local' },
        );
    },
});

export const catalogRagSettingsOp = createAsyncOp({
    name: 'office/catalog_rag_settings',
    successToastKey: 'documents:toast.catalog_rag_settings_saved',
    errorToastKey: 'documents:toast.catalog_rag_settings_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'office/catalogs/rag_settings_requested',
    restMirror: {
        method: 'PATCH',
        path: '/documents/api/v1/catalogs/:catalog_id/rag-index/settings',
    },
    onSuccess: (ctx, _result, event: PlatformEvent) => {
        const catalogId = catalogIdOf(event.payload, 'office/catalog_rag_settings');
        ctx.dispatch(
            catalogRagStatusOp.events.REQUESTED,
            { catalog_id: catalogId },
            { causation_id: event.id, source: 'local' },
        );
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'office/catalog_rag_status': typeof catalogRagStatusOp;
        'office/catalog_rag_enable': typeof catalogRagEnableOp;
        'office/catalog_rag_disable': typeof catalogRagDisableOp;
        'office/catalog_rag_rebuild': typeof catalogRagRebuildOp;
        'office/catalog_rag_settings': typeof catalogRagSettingsOp;
    }
}
