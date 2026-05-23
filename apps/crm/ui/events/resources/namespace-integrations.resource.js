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
            : '/crm/namespaces';
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

export const namespaceIntegrationAutoSyncOp = createAsyncOp({
    name: 'crm/namespace_integration_auto_sync',
    successToastKey: 'crm:toast.integration_auto_sync.saved',
    errorToastKey: 'crm:toast.integration_auto_sync.failed',
    restMirror: {
        method: 'PATCH',
        path: '/crm/api/v1/namespaces/:namespace_name/integrations/:provider/auto-sync',
    },
    request: async ({ payload }) => {
        if (!payload || typeof payload.namespace_name !== 'string') {
            throw new Error('namespaceIntegrationAutoSyncOp: namespace_name обязателен');
        }
        if (!payload || typeof payload.provider_id !== 'string' || payload.provider_id.length === 0) {
            throw new Error('namespaceIntegrationAutoSyncOp: provider_id обязателен');
        }
        if (typeof payload.auto_sync_enabled !== 'boolean') {
            throw new Error('namespaceIntegrationAutoSyncOp: auto_sync_enabled (boolean) обязателен');
        }
        const body = {
            auto_sync_enabled: payload.auto_sync_enabled,
            auto_sync_cron: typeof payload.auto_sync_cron === 'string' ? payload.auto_sync_cron : null,
            auto_sync_timezone: typeof payload.auto_sync_timezone === 'string' ? payload.auto_sync_timezone : 'UTC',
        };
        return await httpRequest({
            method: 'PATCH',
            url: `/crm/api/v1/namespaces/${encodeURIComponent(
                payload.namespace_name,
            )}/integrations/${encodeURIComponent(payload.provider_id)}/auto-sync`,
            body,
        });
    },
});

export const namespaceIntegrationAutoNoteAiOp = createAsyncOp({
    name: 'crm/namespace_integration_auto_note_ai',
    successToastKey: 'crm:toast.integration_auto_note_ai.saved',
    errorToastKey: 'crm:toast.integration_auto_note_ai.failed',
    restMirror: {
        method: 'PATCH',
        path: '/crm/api/v1/namespaces/:namespace_name/integrations/:provider/auto-note-ai-analyze',
    },
    request: async ({ payload }) => {
        if (!payload || typeof payload.namespace_name !== 'string') {
            throw new Error('namespaceIntegrationAutoNoteAiOp: namespace_name обязателен');
        }
        if (!payload || typeof payload.provider_id !== 'string' || payload.provider_id.length === 0) {
            throw new Error('namespaceIntegrationAutoNoteAiOp: provider_id обязателен');
        }
        if (typeof payload.auto_note_ai_analyze !== 'boolean') {
            throw new Error('namespaceIntegrationAutoNoteAiOp: auto_note_ai_analyze (boolean) обязателен');
        }
        return await httpRequest({
            method: 'PATCH',
            url: `/crm/api/v1/namespaces/${encodeURIComponent(
                payload.namespace_name,
            )}/integrations/${encodeURIComponent(payload.provider_id)}/auto-note-ai-analyze`,
            body: { auto_note_ai_analyze: payload.auto_note_ai_analyze },
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
