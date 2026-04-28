/**
 * Namespace Templates — шаблоны namespace со схемой entity-types.
 *
 * Backend (`/crm/api/v1/namespaces/templates`):
 *   GET    /                                → OffsetPage[NamespaceTemplateResponse]
 *   GET    /schema/options                  → NamespaceTemplateSchemaOptionsResponse
 *   POST   /                                → NamespaceTemplateResponse  (create)
 *   GET    /{template_id}                   → NamespaceTemplateDetailsResponse
 *   PUT    /{template_id}                   → NamespaceTemplateResponse  (update via PUT)
 *   DELETE /{template_id}                   → 204                         (remove)
 *   POST   /{template_id}/types             → NamespaceTemplateTypeResponse
 *   DELETE /{template_id}/types/{type_id}   → 204
 *   GET    /{template_id}/task-board-editor-state → TaskBoardEditorStateResponse
 *
 * `update` идёт отдельным `templateUpdateOp` (PUT) — createResourceCollection
 * шлёт PATCH, который CRM не принимает.
 */

import {
    createResourceCollection,
    createAsyncOp,
} from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const templatesResource = createResourceCollection({
    name: 'crm/templates',
    baseUrl: '/crm/api/v1/namespaces/templates',
    idField: 'template_id',
    operations: ['list', 'get', 'create', 'remove'],
    listQuery: () => ({ limit: 200, offset: 0 }),
    toastKeys: {
        create: 'crm:toast.template.created',
        remove: 'crm:toast.template.removed',
    },
});

export const templateUpdateOp = createAsyncOp({
    name: 'crm/template_update',
    successToastKey: 'crm:toast.template.updated',
    errorToastKey: 'crm:toast.template.update_failed',
    restMirror: { method: 'PUT', path: '/crm/api/v1/namespaces/templates/:template_id' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.template_id !== 'string' || !payload.body) {
            throw new Error('templateUpdateOp: { template_id, body } required');
        }
        return await httpRequest({
            method: 'PUT',
            url: `/crm/api/v1/namespaces/templates/${encodeURIComponent(payload.template_id)}`,
            body: payload.body,
        });
    },
});

export const templateSchemaOptionsOp = createAsyncOp({
    name: 'crm/template_schema_options',
    silent: true,
    restMirror: { method: 'GET', path: '/crm/api/v1/namespaces/templates/schema/options' },
    request: async () => {
        return await httpRequest({
            method: 'GET',
            url: '/crm/api/v1/namespaces/templates/schema/options',
        });
    },
});

export const templateTypeUpsertOp = createAsyncOp({
    name: 'crm/template_type_upsert',
    successToastKey: 'crm:toast.template_type.upserted',
    errorToastKey: 'crm:toast.template_type.upsert_failed',
    restMirror: { method: 'POST', path: '/crm/api/v1/namespaces/templates/:template_id/types' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.template_id !== 'string' || !payload.body) {
            throw new Error('templateTypeUpsertOp: { template_id, body } required');
        }
        return await httpRequest({
            method: 'POST',
            url: `/crm/api/v1/namespaces/templates/${encodeURIComponent(payload.template_id)}/types`,
            body: payload.body,
        });
    },
});

export const templateTypeDeleteOp = createAsyncOp({
    name: 'crm/template_type_delete',
    successToastKey: 'crm:toast.template_type.removed',
    errorToastKey: 'crm:toast.template_type.remove_failed',
    restMirror: { method: 'DELETE', path: '/crm/api/v1/namespaces/templates/:template_id/types/:type_id' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.template_id !== 'string' || typeof payload.type_id !== 'string') {
            throw new Error('templateTypeDeleteOp: { template_id, type_id } required');
        }
        await httpRequest({
            method: 'DELETE',
            url: `/crm/api/v1/namespaces/templates/${encodeURIComponent(payload.template_id)}/types/${encodeURIComponent(payload.type_id)}`,
        });
        return { template_id: payload.template_id, type_id: payload.type_id };
    },
});

export const templateTaskBoardEditorStateOp = createAsyncOp({
    name: 'crm/template_task_board_editor_state',
    silent: true,
    restMirror: {
        method: 'GET',
        path: '/crm/api/v1/namespaces/templates/:template_id/task-board-editor-state',
    },
    request: async ({ payload }) => {
        if (!payload || typeof payload.template_id !== 'string' || payload.template_id.length === 0) {
            throw new Error('templateTaskBoardEditorStateOp: payload.template_id required');
        }
        return await httpRequest({
            method: 'GET',
            url: `/crm/api/v1/namespaces/templates/${encodeURIComponent(payload.template_id)}/task-board-editor-state`,
        });
    },
});
