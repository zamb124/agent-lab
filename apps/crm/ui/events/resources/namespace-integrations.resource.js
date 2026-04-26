/**
 * Список интеграций namespace (манифест с бэкенда).
 */

import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const namespaceIntegrationsListOp = createAsyncOp({
    name: 'crm/namespace_integrations_list',
    silent: true,
    restMirror: {
        method: 'GET',
        path: '/crm/api/v1/namespaces/:namespace_name/integrations',
    },
    request: async ({ payload }) => {
        if (!payload || typeof payload.namespace_name !== 'string') {
            throw new Error('namespaceIntegrationsListOp: namespace_name обязателен');
        }
        return await httpRequest({
            method: 'GET',
            url: `/crm/api/v1/namespaces/${encodeURIComponent(
                payload.namespace_name,
            )}/integrations`,
        });
    },
});

export const namespaceIntegrationAuthorizeOp = createAsyncOp({
    name: 'crm/namespace_integration_authorize',
    silent: true,
    restMirror: {
        method: 'GET',
        path: '/crm/api/v1/namespaces/:namespace_name/integrations/:provider/authorize',
    },
    request: async ({ payload }) => {
        if (!payload || typeof payload.namespace_name !== 'string') {
            throw new Error('namespaceIntegrationAuthorizeOp: namespace_name обязателен');
        }
        if (!payload || typeof payload.provider_id !== 'string' || payload.provider_id.length === 0) {
            throw new Error('namespaceIntegrationAuthorizeOp: provider_id обязателен');
        }
        let sub = null;
        if (typeof payload.subdomain === 'string' && payload.subdomain.length > 0) {
            sub = payload.subdomain;
        } else if (typeof payload.amocrm_subdomain === 'string' && payload.amocrm_subdomain.length > 0) {
            sub = payload.amocrm_subdomain;
        }
        if (sub === null) {
            throw new Error('namespaceIntegrationAuthorizeOp: subdomain (или amocrm_subdomain) обязателен');
        }
        const rp = typeof payload.return_path === 'string' && payload.return_path.length > 0
            ? payload.return_path
            : '/crm/spaces';
        const qs = new URLSearchParams();
        qs.set('subdomain', sub);
        qs.set('return_path', rp);
        if (
            typeof globalThis !== 'undefined'
            && globalThis.location
            && typeof globalThis.location.origin === 'string'
            && globalThis.location.origin.length > 0
        ) {
            qs.set('return_origin', globalThis.location.origin);
        }
        const data = await httpRequest({
            method: 'GET',
            url: `/crm/api/v1/namespaces/${encodeURIComponent(
                payload.namespace_name,
            )}/integrations/${encodeURIComponent(payload.provider_id)}/authorize?${qs.toString()}`,
        });
        if (!data || typeof data.authorize_url !== 'string') {
            throw new Error('namespaceIntegrationAuthorizeOp: в ответе нет authorize_url');
        }
        return data.authorize_url;
    },
});

export const namespaceIntegrationEntitiesSyncOp = createAsyncOp({
    name: 'crm/namespace_integration_entities_sync',
    silent: true,
    restMirror: {
        method: 'POST',
        path: '/crm/api/v1/namespaces/:namespace_name/integrations/:provider/sync',
    },
    request: async ({ payload }) => {
        if (!payload || typeof payload.namespace_name !== 'string') {
            throw new Error('namespaceIntegrationEntitiesSyncOp: namespace_name обязателен');
        }
        if (!payload || typeof payload.provider_id !== 'string' || payload.provider_id.length === 0) {
            throw new Error('namespaceIntegrationEntitiesSyncOp: provider_id обязателен');
        }
        return await httpRequest({
            method: 'POST',
            url: `/crm/api/v1/namespaces/${encodeURIComponent(
                payload.namespace_name,
            )}/integrations/${encodeURIComponent(payload.provider_id)}/sync`,
        });
    },
});

export const namespaceIntegrationCustomFieldsSyncOp = createAsyncOp({
    name: 'crm/namespace_integration_custom_fields_sync',
    silent: true,
    restMirror: {
        method: 'POST',
        path: '/crm/api/v1/namespaces/:namespace_name/integrations/:provider/custom_fields/sync',
    },
    request: async ({ payload }) => {
        if (!payload || typeof payload.namespace_name !== 'string') {
            throw new Error('namespaceIntegrationCustomFieldsSyncOp: namespace_name обязателен');
        }
        if (!payload || typeof payload.provider_id !== 'string' || payload.provider_id.length === 0) {
            throw new Error('namespaceIntegrationCustomFieldsSyncOp: provider_id обязателен');
        }
        return await httpRequest({
            method: 'POST',
            url: `/crm/api/v1/namespaces/${encodeURIComponent(
                payload.namespace_name,
            )}/integrations/${encodeURIComponent(payload.provider_id)}/custom_fields/sync`,
        });
    },
});
