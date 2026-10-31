/**
 * Grants — выдача доступа к сущностям и namespace.
 *
 * Backend:
 *   GET    /crm/api/v1/grants?resource_type=&resource_id=
 *   POST   /crm/api/v1/grants
 *   GET    /crm/api/v1/grants/{grant_id}
 *   DELETE /crm/api/v1/grants/{grant_id}  → 204
 *
 * Одна команда на verb: crm/grants/{list,create,item,remove}_requested.
 * Payload: { resource_type, resource_id, subject, user_id?, company_id?, role? }.
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import type { AccessGrantResponse } from '@platform/lib/events/wire/crm.gen.js';

function isAccessGrant(value: unknown): value is AccessGrantResponse {
    return (
        isPlainRecord(value)
        && typeof value.grant_id === 'string'
        && typeof value.resource_type === 'string'
        && typeof value.resource_id === 'string'
        && typeof value.grant_type === 'string'
        && typeof value.role === 'string'
    );
}

const GRANT_CREATE_SUCCEEDED = 'crm/grant_create/succeeded';
const GRANT_REVOKE_SUCCEEDED = 'crm/grant_revoke/succeeded';

function _sameResource(listRequest: unknown, grant: Record<string, unknown>) {
    if (!isPlainRecord(listRequest)) return false;
    return listRequest.resource_type === grant.resource_type
        && listRequest.resource_id === grant.resource_id;
}

/**
 * Список грантов ресурса; исходы create/revoke мержатся сюда, без повторной загрузки.
 */
export const grantsListOp = createAsyncOp({
    name: 'crm/grants_list',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/grants/list_requested',
    restMirror: { method: 'GET', path: '/crm/api/v1/grants' },
    extraReducer: (state, event) => {
        const page = state.lastResult;
        if (page === null || !state.lastRequest) {
            return state;
        }
        const items = page.items;
        if (event.type === GRANT_CREATE_SUCCEEDED) {
            const payload = isPlainRecord(event.payload) ? event.payload : null;
            const grant = payload !== null && isAccessGrant(payload.result) ? payload.result : null;
            if (grant === null || !_sameResource(state.lastRequest.payload, grant)) {
                return state;
            }
            if (items.some((item) => item.grant_id === grant.grant_id)) {
                return state;
            }
            return { ...state, lastResult: { ...page, items: [...items, grant], total: page.total + 1 } };
        }
        if (event.type === GRANT_REVOKE_SUCCEEDED) {
            const payload = isPlainRecord(event.payload) ? event.payload : null;
            const request = payload !== null && isPlainRecord(payload.request) ? payload.request : null;
            const grantId = request !== null && typeof request.grant_id === 'string' ? request.grant_id : '';
            if (grantId.length === 0 || !items.some((item) => item.grant_id === grantId)) {
                return state;
            }
            const nextItems = items.filter((item) => item.grant_id !== grantId);
            return { ...state, lastResult: { ...page, items: nextItems, total: Math.max(0, page.total - 1) } };
        }
        return state;
    },
});

export const grantCreateOp = createAsyncOp({
    name: 'crm/grant_create',
    successToastKey: 'crm:toast.grant.created',
    errorToastKey: 'crm:toast.grant.create_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/grants/create_requested',
    restMirror: { method: 'POST', path: '/crm/api/v1/grants' },
});

export const grantItemOp = createAsyncOp({
    name: 'crm/grant_item',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/grants/item_requested',
    restMirror: { method: 'GET', path: '/crm/api/v1/grants/:grant_id' },
});

export const grantRevokeOp = createAsyncOp({
    name: 'crm/grant_revoke',
    successToastKey: 'crm:toast.grant.revoked',
    errorToastKey: 'crm:toast.grant.revoke_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/grants/remove_requested',
    restMirror: { method: 'DELETE', path: '/crm/api/v1/grants/:grant_id' },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'crm/grants_list': typeof grantsListOp;
        'crm/grant_create': typeof grantCreateOp;
        'crm/grant_item': typeof grantItemOp;
        'crm/grant_revoke': typeof grantRevokeOp;
    }
}
