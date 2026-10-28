/**
 * Office Catalog Members — доступ к приватным каталогам.
 *
 * GET/POST /catalogs/{catalog_id}/members, DELETE /{member_user_id}.
 * Slice `{ items, loadedCatalogId }`. Add/remove после успеха перезапускают list.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import type { PlatformEvent } from '@platform/lib/events/contract.js';

type EventPayload = Record<string, unknown>;

export const catalogMembersOp = createAsyncOp({
    name: 'office/catalog_members',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'office/catalogs/members_list_requested',
    restMirror: { method: 'GET', path: '/documents/api/v1/catalogs/:catalog_id/members' },
    extraInitial: { items: [], loadedCatalogId: null },
    extraReducer: (state, event, events) => {
        if (event.type === events.REQUESTED) {
            const payload = event.payload as EventPayload | null;
            const catalogId = payload && payload.catalog_id;
            if (typeof catalogId !== 'string' || catalogId.length === 0) {
                throw new Error('office/catalog_members: REQUESTED.payload.catalog_id required');
            }
            return { ...state, items: [], loadedCatalogId: catalogId };
        }
        if (event.type === events.SUCCEEDED) {
            const result = (event.payload as EventPayload | null)?.result as { members?: unknown } | null;
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
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'office/catalogs/member_add_requested',
    restMirror: { method: 'POST', path: '/documents/api/v1/catalogs/:catalog_id/members' },
    onSuccess: (ctx, _result, event: PlatformEvent) => {
        const payload = event.payload as EventPayload | null;
        ctx.dispatch(
            catalogMembersOp.events.REQUESTED,
            { catalog_id: payload && payload.catalog_id },
            { causation_id: event.id, source: 'local' },
        );
    },
});

export const catalogMemberRemoveOp = createAsyncOp({
    name: 'office/catalog_member_remove',
    successToastKey: 'documents:toast.catalog_member_removed',
    errorToastKey: 'documents:toast.catalog_member_remove_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'office/catalogs/member_remove_requested',
    restMirror: { method: 'DELETE', path: '/documents/api/v1/catalogs/:catalog_id/members/:member_user_id' },
    onSuccess: (ctx, _result, event: PlatformEvent) => {
        const payload = event.payload as EventPayload | null;
        ctx.dispatch(
            catalogMembersOp.events.REQUESTED,
            { catalog_id: payload && payload.catalog_id },
            { causation_id: event.id, source: 'local' },
        );
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'office/catalog_members': typeof catalogMembersOp;
        'office/catalog_member_add': typeof catalogMemberAddOp;
        'office/catalog_member_remove': typeof catalogMemberRemoveOp;
    }
}
