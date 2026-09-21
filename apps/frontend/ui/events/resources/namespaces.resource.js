/**
 * Console namespaces — company_workspace + personal (admin):
 * команды `frontend/namespaces/{list,create}_requested`, REST-зеркало `apps/frontend/api/namespaces.py`.
 */

import { createResourceCollection, createForm } from '@platform/lib/events/index.js';

export const consoleNamespacesResource = createResourceCollection({
    name: 'frontend/namespaces',
    baseUrl: '/frontend/api/namespaces',
    idField: 'name',
    operations: ['list', 'create'],
    transport: 'ws',
    wsTimeoutMs: 8_000,
    listQuery: () => ({ limit: 200, offset: 0 }),
    toastKeys: {
        create: 'frontend:namespaces_page.toast_created',
        create_error: 'frontend:namespaces_page.toast_create_failed',
    },
});

export const consoleNamespaceCreateForm = createForm({
    name: 'frontend/namespace_create_form',
    submittingClearOnEventTypes: [
        consoleNamespacesResource.events.CREATED,
        consoleNamespacesResource.events.CREATE_FAILED,
    ],
    schema: {
        name: { type: 'string', required: true },
        description: { type: 'string', required: false },
    },
    initial: {
        name: '',
        description: '',
    },
    submitEvent: consoleNamespacesResource.events.CREATE_REQUESTED,
});
