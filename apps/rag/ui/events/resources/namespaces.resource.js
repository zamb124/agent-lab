/**
 * Namespaces — пространства данных RAG-сервиса.
 *
 * Backend (`/rag/api/v1/namespaces`):
 *   GET    /                       → OffsetPage[Namespace] { items, total, limit, offset }
 *   POST   /                       → Namespace
 *   DELETE /{namespace_id}         → { success, name }
 *
 * idField — `name` (Namespace.name уникален в пределах company_id; в URL
 * параметр называется `namespace_id`, но фактически это name). restMirror
 * для `remove` указывает реальный шаблон FastAPI `:namespace_id`.
 *
 * `namespaceCreateForm` — отдельная фабрика формы; submitEvent ведёт в
 * CREATE_REQUESTED резерса. Open/close — из `namespace-create-modal.js`.
 */

import {
    createResourceCollection,
    createForm,
} from '@platform/lib/events/index.js';

const NAMESPACE_NAME_PATTERN = /^[a-z][a-z0-9_-]{0,62}[a-z0-9]$|^[a-z]$/;

export const namespacesResource = createResourceCollection({
    name: 'rag/namespaces',
    baseUrl: '/rag/api/v1/namespaces',
    idField: 'name',
    operations: ['list', 'create', 'remove'],
    listQuery: () => ({ limit: 200, offset: 0 }),
    restMirror: {
        list:   { method: 'GET',    path: '/rag/api/v1/namespaces' },
        create: { method: 'POST',   path: '/rag/api/v1/namespaces' },
        remove: { method: 'DELETE', path: '/rag/api/v1/namespaces/:namespace_id' },
    },
    toastKeys: {
        create: 'rag:toast.namespace_created',
        create_error: 'rag:toast.namespace_create_failed',
        remove: 'rag:toast.namespace_deleted',
        remove_error: 'rag:toast.namespace_delete_failed',
    },
});

export const namespaceCreateForm = createForm({
    name: 'rag/namespace_create_form',
    schema: {
        name: {
            required: true,
            minLength: 1,
            maxLength: 64,
            pattern: NAMESPACE_NAME_PATTERN,
            errorKey: 'form.namespace_name_required',
        },
        description: {
            maxLength: 512,
        },
    },
    initial: { name: '', description: '' },
    submitEvent: namespacesResource.events.CREATE_REQUESTED,
    buildPayload: (draft) => {
        const name = typeof draft.name === 'string' ? draft.name.trim() : '';
        const trimmed_description = typeof draft.description === 'string'
            ? draft.description.trim()
            : '';
        return {
            name,
            description: trimmed_description.length === 0 ? null : trimmed_description,
        };
    },
});
