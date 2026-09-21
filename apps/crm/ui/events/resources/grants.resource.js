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

const GRANT_CREATE_SUCCEEDED = 'crm/grant_create/succeeded';
const GRANT_REVOKE_SUCCEEDED = 'crm/grant_revoke/succeeded';

function _sameResource(listRequest, grant) {
    return (
        listRequest !== null
        && typeof listRequest === 'object'
        && listRequest.resource_type === grant.resource_type
        && listRequest.resource_id === grant.resource_id
    );
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
        if (!page || !Array.isArray(page.items) || !state.lastRequest) {
            return state;
        }
        if (event.type === GRANT_CREATE_SUCCEEDED) {
            const grant = event.payload.result;
            if (!grant || typeof grant.grant_id !== 'string' || !_sameResource(state.lastRequest.payload, grant)) {
                return state;
            }
            if (page.items.some((item) => item && item.grant_id === grant.grant_id)) {
                return state;
            }
            const total = typeof page.total === 'number' ? page.total + 1 : page.total;
            return { ...state, lastResult: { ...page, items: [...page.items, grant], total } };
        }
        if (event.type === GRANT_REVOKE_SUCCEEDED) {
            const request = event.payload.request;
            const grantId = request && typeof request.grant_id === 'string' ? request.grant_id : '';
            if (grantId.length === 0 || !page.items.some((item) => item && item.grant_id === grantId)) {
                return state;
            }
            const items = page.items.filter((item) => !item || item.grant_id !== grantId);
            const total = typeof page.total === 'number' ? Math.max(0, page.total - 1) : page.total;
            return { ...state, lastResult: { ...page, items, total } };
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
