/**
 * Namespaces — пространства CRM компании.
 *
 * Backend (`/crm/api/v1/namespaces`):
 *   GET    /                    → OffsetPage[NamespaceResponse]
 *   POST   /                    → NamespaceResponse              (create)
 *   PUT    /{name}              → NamespaceResponse              (update via PUT)
 *   GET    /{name}/editability  → NamespaceEditabilityResponse   (отдельный op)
 *
 * `update` не входит в operations: createResourceCollection шлёт PATCH, а CRM
 * принимает PUT — поэтому редактирование собирается отдельным
 * `namespaceUpdateOp` (createAsyncOp с явным PUT).
 *
 * idField — `name` (namespace.name уникален в пределах company_id).
 */

import {
    createResourceCollection,
    createAsyncOp,
    createForm,
} from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

const NAMESPACE_NAME_PATTERN = /^[a-z][a-z0-9_]*$/;

export const namespacesResource = createResourceCollection({
    name: 'crm/namespaces',
    baseUrl: '/crm/api/v1/namespaces',
    idField: 'name',
    operations: ['list', 'create'],
    listQuery: () => ({ limit: 200, offset: 0 }),
    toastKeys: {
        create: 'crm:toast.namespace.created',
        create_error: 'crm:toast.namespace.create_failed',
    },
});

export const namespaceUpdateOp = createAsyncOp({
    name: 'crm/namespace_update',
    successToastKey: 'crm:toast.namespace.updated',
    errorToastKey: 'crm:toast.namespace.update_failed',
    restMirror: { method: 'PUT', path: '/crm/api/v1/namespaces/:namespace_name' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.name !== 'string' || !payload.body) {
            throw new Error('namespaceUpdateOp: { name, body } required');
        }
        return await httpRequest({
            method: 'PUT',
            url: `/crm/api/v1/namespaces/${encodeURIComponent(payload.name)}`,
            body: payload.body,
        });
    },
});

export const namespaceEditabilityOp = createAsyncOp({
    name: 'crm/namespace_editability',
    silent: true,
    restMirror: { method: 'GET', path: '/crm/api/v1/namespaces/:namespace_name/editability' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.name !== 'string' || payload.name.length === 0) {
            throw new Error('namespaceEditabilityOp: payload.name required');
        }
        return await httpRequest({
            method: 'GET',
            url: `/crm/api/v1/namespaces/${encodeURIComponent(payload.name)}/editability`,
        });
    },
});

export const namespaceCreateForm = createForm({
    name: 'crm/namespace_create_form',
    schema: {
        template_id: {
            required: true,
            errorKey: 'namespace_modal.err_template_required',
        },
        name: {
            required: true,
            maxLength: 64,
            pattern: NAMESPACE_NAME_PATTERN,
            errorKey: 'namespace_modal.err_name_invalid',
        },
        description: {
            maxLength: 1024,
        },
    },
    initial: { template_id: '', name: '', description: '' },
    submitEvent: namespacesResource.events.CREATE_REQUESTED,
    buildPayload: (draft) => {
        const trimmed_description = typeof draft.description === 'string'
            ? draft.description.trim()
            : '';
        return {
            template_id: draft.template_id,
            name: draft.name.trim(),
            description: trimmed_description.length === 0 ? null : trimmed_description,
        };
    },
});

export const namespaceEditForm = createForm({
    name: 'crm/namespace_edit_form',
    schema: {
        name: {
            required: true,
            errorKey: 'namespace_modal.err_name_required',
        },
        description: {
            maxLength: 1024,
        },
    },
    initial: { name: '', description: '' },
    submitEvent: namespaceUpdateOp.events.REQUESTED,
    buildPayload: (draft) => {
        const trimmed_description = typeof draft.description === 'string'
            ? draft.description.trim()
            : '';
        return {
            name: draft.name,
            body: {
                description: trimmed_description.length === 0 ? null : trimmed_description,
            },
        };
    },
});
