/**
 * Office Namespaces — рабочие пространства компании.
 *
 * Backend (`/documents/api/v1/namespaces`):
 *   GET  /                   → OffsetPage[OfficeNamespaceItem] { items, total, limit, offset }
 *   POST /                   → OfficeNamespaceCreateResponse { name, company_id, description, is_default }
 *
 * Templates: BFF проксирует CRM:
 *   GET /documents/api/v1/namespaces/templates → OffsetPage[OfficeNamespaceTemplateItem]
 *
 * idField — `name` (Namespace.name уникален в пределах company_id).
 * Заголовок `X-Platform-Namespace` подмешивается через `nsHeader(ctx)` —
 * см. `_namespace-header.js`.
 *
 * `namespaceCreateForm` — отдельная фабрика формы для модалки
 * `office.namespace_create`.
 */

import {
    createResourceCollection,
    createAsyncOp,
    createForm,
} from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';
import { nsHeader } from './_namespace-header.js';

const NAMESPACE_NAME_PATTERN = /^[a-z][a-z0-9_]{0,62}[a-z0-9]$|^[a-z]$/;

export const namespacesResource = createResourceCollection({
    name: 'office/namespaces',
    baseUrl: '/documents/api/v1/namespaces',
    idField: 'name',
    operations: ['list', 'create'],
    listQuery: () => ({ limit: 200, offset: 0 }),
    requestHeaders: ({ ctx }) => nsHeader(ctx),
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
    restMirror: { method: 'GET', path: '/documents/api/v1/namespaces/templates' },
    request: ({ ctx }) => httpRequest({
        method: 'GET',
        url: '/documents/api/v1/namespaces/templates',
        query: { limit: 200, offset: 0 },
        headers: nsHeader(ctx),
    }),
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
            name: draft.name.trim(),
            description: trimmed_description.length === 0 ? null : trimmed_description,
        };
    },
});
