/**
 * Office unified access — company, members, public link для catalog и binding.
 *
 * Session-команды идут одним `op_*` через WS RPC и REST-зеркало.
 * Анонимный public browse остаётся HTTP (гостевой pre-WS контур).
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const catalogAccessGetOp = createAsyncOp({
    name: 'office/catalog_access_get',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'office/catalogs/access_requested',
    restMirror: { method: 'GET', path: '/documents/api/v1/catalogs/:catalog_id/access' },
});

export const catalogAccessPatchOp = createAsyncOp({
    name: 'office/catalog_access_update',
    successToastKey: 'documents:toast.access_updated',
    errorToastKey: 'documents:toast.access_update_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'office/catalogs/access_update_requested',
    restMirror: { method: 'PATCH', path: '/documents/api/v1/catalogs/:catalog_id/access' },
});

export const catalogAccessRotateLinkOp = createAsyncOp({
    name: 'office/catalog_access_rotate_link',
    successToastKey: 'documents:toast.access_link_rotated',
    errorToastKey: 'documents:toast.access_link_rotate_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'office/catalogs/access_rotate_link_requested',
    restMirror: { method: 'POST', path: '/documents/api/v1/catalogs/:catalog_id/access/link/rotate' },
});

export const documentAccessGetOp = createAsyncOp({
    name: 'office/document_access_get',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'office/documents/access_requested',
    restMirror: { method: 'GET', path: '/documents/api/v1/documents/:file_id/access' },
});

export const documentAccessPatchOp = createAsyncOp({
    name: 'office/document_access_update',
    successToastKey: 'documents:toast.access_updated',
    errorToastKey: 'documents:toast.access_update_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'office/documents/access_update_requested',
    restMirror: { method: 'PATCH', path: '/documents/api/v1/documents/:file_id/access' },
});

export const documentAccessRotateLinkOp = createAsyncOp({
    name: 'office/document_access_rotate_link',
    successToastKey: 'documents:toast.access_link_rotated',
    errorToastKey: 'documents:toast.access_link_rotate_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'office/documents/access_rotate_link_requested',
    restMirror: { method: 'POST', path: '/documents/api/v1/documents/:file_id/access/link/rotate' },
});

export const publicResolveOp = createAsyncOp({
    name: 'office/public_resolve',
    silent: true,
    restMirror: { method: 'GET', path: '/documents/api/v1/public/resolve/:token' },
    request: ({ payload }) => {
        const reqPayload = payload as { token?: unknown } | null;
        if (!reqPayload || typeof reqPayload.token !== 'string' || reqPayload.token.length === 0) {
            throw new Error('office/public_resolve: payload.token required');
        }
        return httpRequest({
            method: 'GET',
            url: `/documents/api/v1/public/resolve/${encodeURIComponent(reqPayload.token)}`,
        });
    },
});

export const publicOpenOp = createAsyncOp({
    name: 'office/public_open',
    silent: true,
    restMirror: { method: 'GET', path: '/documents/api/v1/public/open/:token' },
    request: ({ payload }) => {
        const reqPayload = payload as { token?: unknown } | null;
        if (!reqPayload || typeof reqPayload.token !== 'string' || reqPayload.token.length === 0) {
            throw new Error('office/public_open: payload.token required');
        }
        return httpRequest({
            method: 'GET',
            url: `/documents/api/v1/public/open/${encodeURIComponent(reqPayload.token)}`,
        });
    },
});

export const publicCatalogBindingOpenOp = createAsyncOp({
    name: 'office/public_catalog_binding_open',
    silent: true,
    restMirror: {
        method: 'GET',
        path: '/documents/api/v1/public/catalog/:token/files/:file_id/open',
    },
    request: ({ payload }) => {
        const reqPayload = payload as { token?: unknown; fileId?: unknown } | null;
        if (!reqPayload || typeof reqPayload.token !== 'string' || reqPayload.token.length === 0) {
            throw new Error('office/public_catalog_binding_open: payload.token required');
        }
        if (typeof reqPayload.fileId !== 'string' || reqPayload.fileId.length === 0) {
            throw new Error('office/public_catalog_binding_open: payload.fileId required');
        }
        return httpRequest({
            method: 'GET',
            url: `/documents/api/v1/public/catalog/${encodeURIComponent(reqPayload.token)}/files/${encodeURIComponent(reqPayload.fileId)}/open`,
        });
    },
});

export const publicCatalogItemsOp = createAsyncOp({
    name: 'office/public_catalog_items',
    silent: true,
    restMirror: { method: 'GET', path: '/documents/api/v1/public/catalog/:token/items' },
    request: ({ payload }) => {
        const reqPayload = payload as { token?: unknown } | null;
        if (!reqPayload || typeof reqPayload.token !== 'string' || reqPayload.token.length === 0) {
            throw new Error('office/public_catalog_items: payload.token required');
        }
        return httpRequest({
            method: 'GET',
            url: `/documents/api/v1/public/catalog/${encodeURIComponent(reqPayload.token)}/items`,
        });
    },
});
