/**
 * Grants — выдача доступа к сущностям и namespace.
 *
 * Backend (entity grants):
 *   GET    /crm/api/v1/entities/{entity_id}/grants            → OffsetPage[AccessGrantResponse]
 *   POST   /crm/api/v1/entities/{entity_id}/grants/public     → AccessGrantResponse
 *   POST   /crm/api/v1/entities/{entity_id}/grants/user       → AccessGrantResponse
 *   POST   /crm/api/v1/entities/{entity_id}/grants/company    → AccessGrantResponse
 *
 * Backend (namespace grants):
 *   GET    /crm/api/v1/namespaces/{namespace}/grants          → OffsetPage[AccessGrantResponse]
 *   POST   /crm/api/v1/namespaces/{namespace}/grants/public   → AccessGrantResponse
 *   POST   /crm/api/v1/namespaces/{namespace}/grants/user     → AccessGrantResponse
 *   POST   /crm/api/v1/namespaces/{namespace}/grants/company  → AccessGrantResponse
 *
 * Backend (revoke):
 *   DELETE /crm/api/v1/grants/{grant_id}                      → 204
 */

import {
    createAsyncOp,
} from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const entityGrantsListOp = createAsyncOp({
    name: 'crm/entity_grants_list',
    silent: true,
    request: async ({ payload }) => {
        if (!payload || typeof payload.entity_id !== 'string') {
            throw new Error('entityGrantsListOp: payload.entity_id required');
        }
        return await httpRequest({
            method: 'GET',
            url: `/crm/api/v1/entities/${encodeURIComponent(payload.entity_id)}/grants?limit=200&offset=0`,
        });
    },
});

export const entityGrantCreateOp = createAsyncOp({
    name: 'crm/entity_grant_create',
    successToastKey: 'crm:toast.grant.created',
    errorToastKey: 'crm:toast.grant.create_failed',
    request: async ({ payload }) => {
        if (!payload || typeof payload.entity_id !== 'string' || typeof payload.subject !== 'string') {
            throw new Error('entityGrantCreateOp: { entity_id, subject, body? } required');
        }
        const url = `/crm/api/v1/entities/${encodeURIComponent(payload.entity_id)}/grants/${payload.subject}`;
        return await httpRequest({
            method: 'POST',
            url,
            body: payload.body === undefined ? null : payload.body,
        });
    },
});

export const namespaceGrantsListOp = createAsyncOp({
    name: 'crm/namespace_grants_list',
    silent: true,
    request: async ({ payload }) => {
        if (!payload || typeof payload.namespace !== 'string') {
            throw new Error('namespaceGrantsListOp: payload.namespace required');
        }
        return await httpRequest({
            method: 'GET',
            url: `/crm/api/v1/namespaces/${encodeURIComponent(payload.namespace)}/grants?limit=200&offset=0`,
        });
    },
});

export const namespaceGrantCreateOp = createAsyncOp({
    name: 'crm/namespace_grant_create',
    successToastKey: 'crm:toast.grant.created',
    errorToastKey: 'crm:toast.grant.create_failed',
    request: async ({ payload }) => {
        if (!payload || typeof payload.namespace !== 'string' || typeof payload.subject !== 'string') {
            throw new Error('namespaceGrantCreateOp: { namespace, subject, body? } required');
        }
        const url = `/crm/api/v1/namespaces/${encodeURIComponent(payload.namespace)}/grants/${payload.subject}`;
        return await httpRequest({
            method: 'POST',
            url,
            body: payload.body === undefined ? null : payload.body,
        });
    },
});

export const grantRevokeOp = createAsyncOp({
    name: 'crm/grant_revoke',
    successToastKey: 'crm:toast.grant.revoked',
    errorToastKey: 'crm:toast.grant.revoke_failed',
    request: async ({ payload }) => {
        if (!payload || typeof payload.grant_id !== 'string') {
            throw new Error('grantRevokeOp: payload.grant_id required');
        }
        await httpRequest({
            method: 'DELETE',
            url: `/crm/api/v1/grants/${encodeURIComponent(payload.grant_id)}`,
        });
        return { grant_id: payload.grant_id };
    },
});
