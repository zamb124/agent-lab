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

export const grantsListOp = createAsyncOp({
    name: 'crm/grants_list',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/grants/list_requested',
    restMirror: { method: 'GET', path: '/crm/api/v1/grants' },
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
