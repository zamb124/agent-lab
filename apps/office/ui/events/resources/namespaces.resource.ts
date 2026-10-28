/**
 * Office Namespaces — рабочие пространства компании.
 *
 * Backend (`/documents/api/v1/namespaces`):
 *   GET  /                   → OffsetPage[Namespace] { items, total, limit, offset }
 *   POST /                   → OfficeNamespaceCreateResponse { name, company_id, description, is_default }
 *
 * Templates: BFF проксирует CRM:
 *   GET /documents/api/v1/namespaces/templates → OffsetPage[OfficeNamespaceTemplateItem]
 *
 * idField — `name` (Namespace.name уникален в пределах company_id).
 * Namespace списка каталогов — `PlatformEvent.meta.namespace`.
 *
 * `namespaceCreateForm` — отдельная фабрика формы для модалки
 * `office.namespace_create`.
 */

import {
    createResourceCollection,
    createAsyncOp,
    createForm,
} from '@platform/lib/events/index.js';

const NAMESPACE_NAME_PATTERN = /^[a-z][a-z0-9_]{0,62}[a-z0-9]$|^[a-z]$/;

export const namespacesResource = createResourceCollection({
    name: 'office/namespaces',
    baseUrl: '/documents/api/v1/namespaces',
    idField: 'name',
    operations: ['list', 'create'],
    transport: 'ws',
    wsTimeoutMs: 8_000,
    listQuery: () => ({ limit: 200, offset: 0 }),
    restMirror: {
        list:   { method: 'GET',  path: '/documents/api/v1/namespaces' },
        create: { method: 'POST', path: '/documents/api/v1/namespaces' },
    },
    toastKeys: {
        create: 'documents:toast.namespace_created',
        create_error: 'documents:toast.namespace_create_failed',
    },
});

export const namespaceTemplatesOp = createAsyncOp({
    name: 'office/namespace_templates',
    silent: true,
    transport: 'ws',
    wsTimeoutMs: 8_000,
    commandType: 'office/namespaces/templates_requested',
    restMirror: { method: 'GET', path: '/documents/api/v1/namespaces/templates' },
});

export const namespaceCreateForm = createForm({
    name: 'office/namespace_create_form',
    schema: {
        template_id: {
            required: true,
            errorKey: 'form.namespace_template_required',
        },
        name: {
            required: true,
            minLength: 1,
            maxLength: 64,
            pattern: NAMESPACE_NAME_PATTERN,
            errorKey: 'form.namespace_name_invalid',
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
            name: String(draft.name).trim(),
            description: trimmed_description.length === 0 ? null : trimmed_description,
        };
    },
});

declare module '@platform/lib/events/factory-registry.js' {
    interface PlatformFactoryRegistry {
        'office/namespaces': typeof namespacesResource;
        'office/namespace_templates': typeof namespaceTemplatesOp;
        'office/namespace_create_form': typeof namespaceCreateForm;
    }
}
