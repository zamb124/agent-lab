/**
 * Boards — доски задач (колонки канбана).
 */

import {
    createResourceCollection,
    createForm,
} from '@platform/lib/events/index.js';

export const boardsResource = createResourceCollection({
    name: 'worktracker/boards',
    baseUrl: '/worktracker/api/v1/boards',
    idField: 'board_id',
    operations: ['list', 'get', 'create', 'update'],
    transport: 'ws',
    wsTimeoutMs: 5_000,
    listQuery: (payload: unknown) => {
        const query: Record<string, string> = {};
        const ns = payload && typeof payload === 'object' ? (payload as Record<string, unknown>).namespace : undefined;
        if (typeof ns === 'string' && ns.length > 0) {
            query.namespace = ns;
        }
        return query;
    },
    toastKeys: {
        create: 'worktracker:toast.board_created',
        create_error: 'worktracker:toast.board_create_failed',
        update: 'worktracker:toast.board_updated',
        update_error: 'worktracker:toast.board_update_failed',
    },
});

export const boardCreateForm = createForm({
    name: 'worktracker/board_create_form',
    schema: {
        name: { required: true, minLength: 1, maxLength: 255, errorKey: 'form.board_name_required' },
    },
    initial: { name: '' },
    submitEvent: boardsResource.events.CREATE_REQUESTED,
    buildPayload: (draft: Record<string, unknown>) => ({
        name: typeof draft.name === 'string' ? draft.name.trim() : '',
        board_key: 'generic',
    }),
});
