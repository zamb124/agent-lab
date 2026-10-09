/**
 * Namespace Templates — шаблоны namespace со схемой entity-types.
 *
 * Backend (`/crm/api/v1/namespaces/templates`):
 *   GET    /                                → OffsetPage[NamespaceTemplateResponse]
 *   GET    /schema/options                  → NamespaceTemplateSchemaOptionsResponse
 *   POST   /                                → NamespaceTemplateResponse
 *   GET    /{template_id}                   → NamespaceTemplateDetailsResponse
 *   PUT    /{template_id}                   → NamespaceTemplateResponse
 *   DELETE /{template_id}                   → 204
 *   POST   /{template_id}/types             → NamespaceTemplateTypeResponse
 *   DELETE /{template_id}/types/{type_id}   → 204
 *
 * `update` идёт отдельным `templateUpdateOp` (PUT) — createResourceCollection
 * шлёт PATCH, который CRM не принимает.
 */

import {
    createResourceCollection,
    createAsyncOp,
    upsertItem,
} from '@platform/lib/events/index.js';

const TEMPLATE_UPDATE_SUCCEEDED = 'crm/template_update/succeeded';

export const templatesResource = createResourceCollection({
    name: 'crm/templates',
    baseUrl: '/crm/api/v1/namespaces/templates',
    idField: 'template_id',
    operations: ['list', 'get', 'create', 'remove'],
    transport: 'ws',
    wsTimeoutMs: 8_000,
    listQuery: () => ({ limit: 200, offset: 0 }),
    toastKeys: {
        create: 'crm:toast.template.created',
        remove: 'crm:toast.template.removed',
    },
    extraReducer: (state, event) => {
        if (event.type !== TEMPLATE_UPDATE_SUCCEEDED) {
            return state;
        }
        const template = (event.payload as Record<string, any>).result;
        if (!template || typeof template.template_id !== 'string') {
            return state;
        }
        return upsertItem(state, template, 'template_id');
    },
});

export const templateUpdateOp = createAsyncOp({
    name: 'crm/template_update',
    successToastKey: 'crm:toast.template.updated',
    errorToastKey: 'crm:toast.template.update_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/templates/update_requested',
    restMirror: { method: 'PUT', path: '/crm/api/v1/namespaces/templates/:template_id' },
});

export const templateSchemaOptionsOp = createAsyncOp({
    name: 'crm/template_schema_options',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/templates/schema_options_requested',
    restMirror: { method: 'GET', path: '/crm/api/v1/namespaces/templates/schema/options' },
});

export const templateTypeUpsertOp = createAsyncOp({
    name: 'crm/template_type_upsert',
    successToastKey: 'crm:toast.template_type.upserted',
    errorToastKey: 'crm:toast.template_type.upsert_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/templates/type_upsert_requested',
    restMirror: { method: 'POST', path: '/crm/api/v1/namespaces/templates/:template_id/types' },
});

export const templateTypeDeleteOp = createAsyncOp({
    name: 'crm/template_type_delete',
    successToastKey: 'crm:toast.template_type.removed',
    errorToastKey: 'crm:toast.template_type.remove_failed',
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'crm/templates/type_remove_requested',
    restMirror: { method: 'DELETE', path: '/crm/api/v1/namespaces/templates/:template_id/types/:type_id' },
});
