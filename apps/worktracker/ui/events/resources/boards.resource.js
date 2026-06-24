/**
 * Boards — доски задач (колонки канбана).
 *
 * Backend (`/worktracker/api/v1/boards`):
 *   GET   /                 → OffsetPage<Board>
 *   GET   /{board_id}       → Board
 *   POST  /                 → Board (create)
 *   PATCH /{board_id}       → Board (update)
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
    transport: 'http',
    listQuery: (payload) => {
        const query = {};
        if (payload && typeof payload === 'object' && typeof payload.namespace === 'string' && payload.namespace.length > 0) {
            query.namespace = payload.namespace;
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
    buildPayload: (draft) => ({
        name: typeof draft.name === 'string' ? draft.name.trim() : '',
        board_key: 'generic',
    }),
});
