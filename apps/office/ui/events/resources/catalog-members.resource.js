/**
 * Office Catalog Members — управление доступом к приватным каталогам.
 *
 * Backend (`/documents/api/v1/catalogs/{catalog_id}/members`):
 *   GET    /                          → OfficeCatalogMembersResponse { members }
 *   POST   /                          → OfficeCatalogMembersResponse (add)
 *   DELETE /{member_user_id}          → 204
 *
 * Sub-resource по `catalogId` — реализован как `createAsyncOp` со slice
 * `{ items, loadedCatalogId }`. Add/remove ops после успеха перезапускают
 * `catalogMembersOp` для перезагрузки списка.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';
import { nsHeader } from './_namespace-header.js';

export const catalogMembersOp = createAsyncOp({
    name: 'office/catalog_members',
    silent: true,
    restMirror: { method: 'GET', path: '/documents/api/v1/catalogs/:catalog_id/members' },
    request: ({ payload, ctx }) => {
        if (!payload || typeof payload.catalogId !== 'string' || payload.catalogId.length === 0) {
            throw new Error('office/catalog_members: payload.catalogId required');
        }
        return httpRequest({
            method: 'GET',
            url: `/documents/api/v1/catalogs/${encodeURIComponent(payload.catalogId)}/members`,
            headers: nsHeader(ctx),
        });
    },
    extraInitial: { items: [], loadedCatalogId: null },
    extraReducer: (state, event, events) => {
        if (event.type === events.REQUESTED) {
            const catalogId = event.payload && event.payload.catalogId;
            if (typeof catalogId !== 'string') {
                throw new Error('office/catalog_members: REQUESTED.payload.catalogId required');
            }
            return { ...state, items: [], loadedCatalogId: catalogId };
        }
        if (event.type === events.SUCCEEDED) {
            const result = event.payload.result;
            if (!result || !Array.isArray(result.members)) {
                throw new Error('office/catalog_members: SUCCEEDED.result.members required (array)');
            }
            return { ...state, items: result.members };
        }
        return state;
    },
});

export const catalogMemberAddOp = createAsyncOp({
    name: 'office/catalog_member_add',
    successToastKey: 'documents:toast.catalog_member_added',
    errorToastKey: 'documents:toast.catalog_member_add_failed',
    restMirror: { method: 'POST', path: '/documents/api/v1/catalogs/:catalog_id/members' },
    request: ({ payload, ctx }) => {
        if (!payload || typeof payload.catalogId !== 'string') {
            throw new Error('office/catalog_member_add: payload.catalogId required');
        }
        if (typeof payload.userId !== 'string' || payload.userId.length === 0) {
            throw new Error('office/catalog_member_add: payload.userId required');
        }
        return httpRequest({
            method: 'POST',
            url: `/documents/api/v1/catalogs/${encodeURIComponent(payload.catalogId)}/members`,
            body: { user_id: payload.userId },
            headers: nsHeader(ctx),
        });
    },
    onSuccess: (ctx, _result, event) => {
        ctx.dispatch(
            catalogMembersOp.events.REQUESTED,
            { catalogId: event.payload.catalogId },
            { causation_id: event.id, source: 'local' },
        );
    },
});

export const catalogMemberRemoveOp = createAsyncOp({
    name: 'office/catalog_member_remove',
    successToastKey: 'documents:toast.catalog_member_removed',
    errorToastKey: 'documents:toast.catalog_member_remove_failed',
    restMirror: { method: 'DELETE', path: '/documents/api/v1/catalogs/:catalog_id/members/:member_user_id' },
    request: ({ payload, ctx }) => {
        if (!payload || typeof payload.catalogId !== 'string') {
            throw new Error('office/catalog_member_remove: payload.catalogId required');
        }
        if (typeof payload.userId !== 'string' || payload.userId.length === 0) {
            throw new Error('office/catalog_member_remove: payload.userId required');
        }
        return httpRequest({
            method: 'DELETE',
            url: `/documents/api/v1/catalogs/${encodeURIComponent(payload.catalogId)}/members/${encodeURIComponent(payload.userId)}`,
            headers: nsHeader(ctx),
        });
    },
    onSuccess: (ctx, _result, event) => {
        ctx.dispatch(
            catalogMembersOp.events.REQUESTED,
            { catalogId: event.payload.catalogId },
            { causation_id: event.id, source: 'local' },
        );
    },
});
