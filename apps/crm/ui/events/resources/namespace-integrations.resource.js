/**
 * Список интеграций namespace (манифест с бэкенда).
 */

import { createAsyncOp } from '@platform/lib/events/index.js';

export const namespaceIntegrationsListOp = createAsyncOp({
    name: 'crm/namespace_integrations_list',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/namespace_integrations/list_requested',
    restMirror: {
        method: 'GET',
        path: '/crm/api/v1/namespaces/:namespace_name/integrations',
    },
});

export const namespaceIntegrationAuthorizeOp = createAsyncOp({
    name: 'crm/namespace_integration_authorize',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/namespace_integrations/authorize_requested',
    restMirror: {
        method: 'GET',
        path: '/crm/api/v1/namespaces/:namespace_name/integrations/:provider/authorize',
    },
});

export const namespaceIntegrationEntitiesSyncOp = createAsyncOp({
    name: 'crm/namespace_integration_entities_sync',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/namespace_integrations/sync_requested',
    restMirror: {
        method: 'POST',
        path: '/crm/api/v1/namespaces/:namespace_name/integrations/:provider/sync',
    },
});

export const namespaceIntegrationAutoSyncOp = createAsyncOp({
    name: 'crm/namespace_integration_auto_sync',
    successToastKey: 'crm:toast.integration_auto_sync.saved',
    errorToastKey: 'crm:toast.integration_auto_sync.failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/namespace_integrations/auto_sync_requested',
    restMirror: {
        method: 'PATCH',
        path: '/crm/api/v1/namespaces/:namespace_name/integrations/:provider/auto-sync',
    },
});

export const namespaceIntegrationAutoNoteAiOp = createAsyncOp({
    name: 'crm/namespace_integration_auto_note_ai',
    successToastKey: 'crm:toast.integration_auto_note_ai.saved',
    errorToastKey: 'crm:toast.integration_auto_note_ai.failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/namespace_integrations/auto_note_ai_requested',
    restMirror: {
        method: 'PATCH',
        path: '/crm/api/v1/namespaces/:namespace_name/integrations/:provider/auto-note-ai-analyze',
    },
});

export const namespaceIntegrationCustomFieldsSyncOp = createAsyncOp({
    name: 'crm/namespace_integration_custom_fields_sync',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/namespace_integrations/custom_fields_sync_requested',
    restMirror: {
        method: 'POST',
        path: '/crm/api/v1/namespaces/:namespace_name/integrations/:provider/custom_fields/sync',
    },
});
