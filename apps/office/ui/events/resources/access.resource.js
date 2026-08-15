/**
 * Office unified access — company, members, public link для catalog и binding.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';
import { nsHeader } from './_namespace-header.js';

export const catalogAccessGetOp = createAsyncOp({
    name: 'office/catalog_access_get',
    silent: true,
    restMirror: { method: 'GET', path: '/documents/api/v1/catalogs/:catalog_id/access' },
    request: ({ payload, ctx }) => {
        if (!payload || typeof payload.catalogId !== 'string' || payload.catalogId.length === 0) {
            throw new Error('office/catalog_access_get: payload.catalogId required');
        }
        return httpRequest({
            method: 'GET',
            url: `/documents/api/v1/catalogs/${encodeURIComponent(payload.catalogId)}/access`,
            headers: nsHeader(ctx),
        });
    },
});

export const catalogAccessPatchOp = createAsyncOp({
    name: 'office/catalog_access_update',
    successToastKey: 'documents:toast.access_updated',
    errorToastKey: 'documents:toast.access_update_failed',
    restMirror: { method: 'PATCH', path: '/documents/api/v1/catalogs/:catalog_id/access' },
    request: ({ payload, ctx }) => {
        if (!payload || typeof payload.catalogId !== 'string' || payload.catalogId.length === 0) {
            throw new Error('office/catalog_access_update: payload.catalogId required');
        }
        return httpRequest({
            method: 'PATCH',
            url: `/documents/api/v1/catalogs/${encodeURIComponent(payload.catalogId)}/access`,
            headers: nsHeader(ctx),
            body: {
                company_visible: payload.companyVisible,
                link_enabled: payload.linkEnabled,
                link_permission: payload.linkPermission,
                members: payload.members,
            },
        });
    },
});

export const catalogAccessRotateLinkOp = createAsyncOp({
    name: 'office/catalog_access_rotate_link',
    successToastKey: 'documents:toast.access_link_rotated',
    errorToastKey: 'documents:toast.access_link_rotate_failed',
    restMirror: { method: 'POST', path: '/documents/api/v1/catalogs/:catalog_id/access/link/rotate' },
    request: ({ payload, ctx }) => {
        if (!payload || typeof payload.catalogId !== 'string' || payload.catalogId.length === 0) {
            throw new Error('office/catalog_access_rotate_link: payload.catalogId required');
        }
        return httpRequest({
            method: 'POST',
            url: `/documents/api/v1/catalogs/${encodeURIComponent(payload.catalogId)}/access/link/rotate`,
            headers: nsHeader(ctx),
        });
    },
});

export const documentAccessGetOp = createAsyncOp({
    name: 'office/document_access_get',
    silent: true,
    restMirror: { method: 'GET', path: '/documents/api/v1/documents/:file_id/access' },
    request: ({ payload, ctx }) => {
        if (!payload || typeof payload.fileId !== 'string' || payload.fileId.length === 0) {
            throw new Error('office/document_access_get: payload.fileId required');
        }
        return httpRequest({
            method: 'GET',
            url: `/documents/api/v1/documents/${encodeURIComponent(payload.fileId)}/access`,
            headers: nsHeader(ctx),
        });
    },
});

export const documentAccessPatchOp = createAsyncOp({
    name: 'office/document_access_update',
    successToastKey: 'documents:toast.access_updated',
    errorToastKey: 'documents:toast.access_update_failed',
    restMirror: { method: 'PATCH', path: '/documents/api/v1/documents/:file_id/access' },
    request: ({ payload, ctx }) => {
        if (!payload || typeof payload.fileId !== 'string' || payload.fileId.length === 0) {
            throw new Error('office/document_access_update: payload.fileId required');
        }
        return httpRequest({
            method: 'PATCH',
            url: `/documents/api/v1/documents/${encodeURIComponent(payload.fileId)}/access`,
            headers: nsHeader(ctx),
            body: {
                link_enabled: payload.linkEnabled,
                link_permission: payload.linkPermission,
                members: payload.members,
            },
        });
    },
});

export const documentAccessRotateLinkOp = createAsyncOp({
    name: 'office/document_access_rotate_link',
    successToastKey: 'documents:toast.access_link_rotated',
    errorToastKey: 'documents:toast.access_link_rotate_failed',
    restMirror: { method: 'POST', path: '/documents/api/v1/documents/:file_id/access/link/rotate' },
    request: ({ payload, ctx }) => {
        if (!payload || typeof payload.fileId !== 'string' || payload.fileId.length === 0) {
            throw new Error('office/document_access_rotate_link: payload.fileId required');
        }
        return httpRequest({
            method: 'POST',
            url: `/documents/api/v1/documents/${encodeURIComponent(payload.fileId)}/access/link/rotate`,
            headers: nsHeader(ctx),
        });
    },
});

export const publicResolveOp = createAsyncOp({
    name: 'office/public_resolve',
    silent: true,
    restMirror: { method: 'GET', path: '/documents/api/v1/public/resolve/:token' },
    request: ({ payload }) => {
        if (!payload || typeof payload.token !== 'string' || payload.token.length === 0) {
            throw new Error('office/public_resolve: payload.token required');
        }
        return httpRequest({
            method: 'GET',
            url: `/documents/api/v1/public/resolve/${encodeURIComponent(payload.token)}`,
        });
    },
});

export const publicOpenOp = createAsyncOp({
    name: 'office/public_open',
    silent: true,
    restMirror: { method: 'GET', path: '/documents/api/v1/public/open/:token' },
    request: ({ payload }) => {
        if (!payload || typeof payload.token !== 'string' || payload.token.length === 0) {
            throw new Error('office/public_open: payload.token required');
        }
        return httpRequest({
            method: 'GET',
            url: `/documents/api/v1/public/open/${encodeURIComponent(payload.token)}`,
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
        if (!payload || typeof payload.token !== 'string' || payload.token.length === 0) {
            throw new Error('office/public_catalog_binding_open: payload.token required');
        }
        if (typeof payload.fileId !== 'string' || payload.fileId.length === 0) {
            throw new Error('office/public_catalog_binding_open: payload.fileId required');
        }
        return httpRequest({
            method: 'GET',
            url: `/documents/api/v1/public/catalog/${encodeURIComponent(payload.token)}/files/${encodeURIComponent(payload.fileId)}/open`,
        });
    },
});

export const publicCatalogItemsOp = createAsyncOp({
    name: 'office/public_catalog_items',
    silent: true,
    restMirror: { method: 'GET', path: '/documents/api/v1/public/catalog/:token/items' },
    request: ({ payload }) => {
        if (!payload || typeof payload.token !== 'string' || payload.token.length === 0) {
            throw new Error('office/public_catalog_items: payload.token required');
        }
        return httpRequest({
            method: 'GET',
            url: `/documents/api/v1/public/catalog/${encodeURIComponent(payload.token)}/items`,
        });
    },
});
