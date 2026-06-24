/**
 * WorkItems — задачи ядра (канбан, очереди, HITL, агентские задачи).
 */

import {
    createResourceCollection,
    createAsyncOp,
    createForm,
} from '@platform/lib/events/index.js';
import { createMultipartFileUploadOp } from '@platform/lib/events/factories/_multipart-upload.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const WORK_ITEM_EVENTS = [
    'worktracker/work_item/created',
    'worktracker/work_item/updated',
    'worktracker/work_item/moved',
    'worktracker/work_item/completed',
    'worktracker/work_item/comment_created',
];

export const WORK_ITEM_MUTATION_SUCCEEDED = [
    'worktracker/work_item_move/succeeded',
    'worktracker/work_item_claim/succeeded',
    'worktracker/work_item_complete/succeeded',
    'worktracker/work_item_cancel/succeeded',
    'worktracker/work_item_assign/succeeded',
];

function _mergeWorkItem(state, item) {
    const id = item.work_item_id;
    const idx = state.items.findIndex((x) => x && x.work_item_id === id);
    const items = idx === -1 ? [...state.items, item] : state.items.map((x, i) => (i === idx ? item : x));
    return { ...state, items, byId: { ...state.byId, [id]: item } };
}

export const worktrackerFileUploadOp = createMultipartFileUploadOp({
    name: 'worktracker/file_upload',
    url: '/worktracker/api/v1/files/',
});

export const workItemsResource = createResourceCollection({
    name: 'worktracker/work_items',
    baseUrl: '/worktracker/api/v1/work-items',
    idField: 'work_item_id',
    operations: ['list', 'get', 'create', 'update'],
    transport: 'http',
    listQuery: (payload) => {
        const query = {};
        if (!payload || typeof payload !== 'object') {
            return query;
        }
        for (const key of [
            'board_id',
            'namespace',
            'kind',
            'state',
            'work_queue_id',
            'assignee_user_id',
            'assignee_flow_id',
        ]) {
            if (typeof payload[key] === 'string' && payload[key].length > 0) {
                query[key] = payload[key];
            }
        }
        if (payload.exclude_terminal === true) {
            query.exclude_terminal = true;
        }
        if (payload.queue_unclaimed_only === true) {
            query.queue_unclaimed_only = true;
        }
        if (Array.isArray(payload.work_queue_ids) && payload.work_queue_ids.length > 0) {
            query.work_queue_ids = payload.work_queue_ids;
        }
        query.limit = typeof payload.limit === 'number' ? payload.limit : 200;
        query.offset = typeof payload.offset === 'number' ? payload.offset : 0;
        return query;
    },
    toastKeys: {
        create: 'worktracker:toast.work_item_created',
        create_error: 'worktracker:toast.work_item_create_failed',
        update: 'worktracker:toast.work_item_updated',
        update_error: 'worktracker:toast.work_item_update_failed',
    },
    extraReducer: (state, event) => {
        if (WORK_ITEM_MUTATION_SUCCEEDED.includes(event.type)) {
            const payload = event.payload;
            if (!payload || typeof payload !== 'object' || !('result' in payload)) {
                return state;
            }
            const item = payload.result;
            if (!item || typeof item !== 'object' || typeof item.work_item_id !== 'string') {
                return state;
            }
            return _mergeWorkItem(state, item);
        }
        if (!WORK_ITEM_EVENTS.includes(event.type)) {
            return state;
        }
        const payload = event.payload;
        if (!payload || typeof payload !== 'object') {
            return state;
        }
        if (event.type === 'worktracker/work_item/comment_created') {
            const workItemId = payload.work_item_id;
            if (typeof workItemId !== 'string') {
                return state;
            }
            const existing = state.byId[workItemId];
            if (!existing || typeof existing !== 'object') {
                return state;
            }
            const commentCount = typeof existing.comment_count === 'number' ? existing.comment_count + 1 : 1;
            const updated = { ...existing, comment_count: commentCount };
            return _mergeWorkItem(state, updated);
        }
        const item = payload.work_item;
        if (!item || typeof item !== 'object' || typeof item.work_item_id !== 'string') {
            return state;
        }
        return _mergeWorkItem(state, item);
    },
});

export const workItemMoveOp = createAsyncOp({
    name: 'worktracker/work_item_move',
    silent: true,
    restMirror: { method: 'POST', path: '/worktracker/api/v1/work-items/:work_item_id/move' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.work_item_id !== 'string') {
            throw new Error('workItemMoveOp: payload.work_item_id required');
        }
        const body = {};
        if (typeof payload.board_column_id === 'string') {
            body.board_column_id = payload.board_column_id;
        }
        if (typeof payload.state === 'string') {
            body.state = payload.state;
        }
        return await httpRequest({
            method: 'POST',
            url: `/worktracker/api/v1/work-items/${encodeURIComponent(payload.work_item_id)}/move`,
            body,
        });
    },
});

export const workItemClaimOp = createAsyncOp({
    name: 'worktracker/work_item_claim',
    successToastKey: 'worktracker:toast.work_item_claimed',
    errorToastKey: 'worktracker:toast.work_item_claim_failed',
    restMirror: { method: 'POST', path: '/worktracker/api/v1/work-items/:work_item_id/claim' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.work_item_id !== 'string') {
            throw new Error('workItemClaimOp: payload.work_item_id required');
        }
        return await httpRequest({
            method: 'POST',
            url: `/worktracker/api/v1/work-items/${encodeURIComponent(payload.work_item_id)}/claim`,
        });
    },
});

export const workItemCompleteOp = createAsyncOp({
    name: 'worktracker/work_item_complete',
    successToastKey: 'worktracker:toast.work_item_completed',
    errorToastKey: 'worktracker:toast.work_item_complete_failed',
    restMirror: { method: 'POST', path: '/worktracker/api/v1/work-items/:work_item_id/complete' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.work_item_id !== 'string') {
            throw new Error('workItemCompleteOp: payload.work_item_id required');
        }
        const body = {
            resolution_text: typeof payload.resolution_text === 'string' ? payload.resolution_text : '',
            resolution_files: Array.isArray(payload.resolution_files) ? payload.resolution_files : [],
        };
        if (typeof payload.terminal_state === 'string') {
            body.terminal_state = payload.terminal_state;
        }
        return await httpRequest({
            method: 'POST',
            url: `/worktracker/api/v1/work-items/${encodeURIComponent(payload.work_item_id)}/complete`,
            body,
        });
    },
});

export const workItemCancelOp = createAsyncOp({
    name: 'worktracker/work_item_cancel',
    successToastKey: 'worktracker:toast.work_item_cancelled',
    errorToastKey: 'worktracker:toast.work_item_cancel_failed',
    restMirror: { method: 'POST', path: '/worktracker/api/v1/work-items/:work_item_id/cancel' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.work_item_id !== 'string') {
            throw new Error('workItemCancelOp: payload.work_item_id required');
        }
        return await httpRequest({
            method: 'POST',
            url: `/worktracker/api/v1/work-items/${encodeURIComponent(payload.work_item_id)}/cancel`,
        });
    },
});

export const workItemAssignOp = createAsyncOp({
    name: 'worktracker/work_item_assign',
    successToastKey: 'worktracker:toast.work_item_assigned',
    errorToastKey: 'worktracker:toast.work_item_assign_failed',
    restMirror: { method: 'POST', path: '/worktracker/api/v1/work-items/:work_item_id/assign' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.work_item_id !== 'string') {
            throw new Error('workItemAssignOp: payload.work_item_id required');
        }
        if (!payload.assignment || typeof payload.assignment !== 'object') {
            throw new Error('workItemAssignOp: payload.assignment required');
        }
        return await httpRequest({
            method: 'POST',
            url: `/worktracker/api/v1/work-items/${encodeURIComponent(payload.work_item_id)}/assign`,
            body: { assignment: payload.assignment },
        });
    },
});

export const workItemCommentOp = createAsyncOp({
    name: 'worktracker/work_item_comment',
    silent: true,
    restMirror: { method: 'POST', path: '/worktracker/api/v1/work-items/:work_item_id/comments' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.work_item_id !== 'string') {
            throw new Error('workItemCommentOp: payload.work_item_id required');
        }
        return await httpRequest({
            method: 'POST',
            url: `/worktracker/api/v1/work-items/${encodeURIComponent(payload.work_item_id)}/comments`,
            body: {
                text: typeof payload.text === 'string' ? payload.text : '',
                files: Array.isArray(payload.files) ? payload.files : [],
            },
        });
    },
});

export const workItemCommentsListOp = createAsyncOp({
    name: 'worktracker/work_item_comments_list',
    silent: true,
    restMirror: { method: 'GET', path: '/worktracker/api/v1/work-items/:work_item_id/comments' },
    extraInitial: { items: [] },
    request: async ({ payload }) => {
        if (!payload || typeof payload.work_item_id !== 'string') {
            throw new Error('workItemCommentsListOp: payload.work_item_id required');
        }
        return await httpRequest({
            method: 'GET',
            url: `/worktracker/api/v1/work-items/${encodeURIComponent(payload.work_item_id)}/comments`,
        });
    },
    extraReducer: (state, event, events) => {
        if (event.type !== events.SUCCEEDED || !event.payload || !('result' in event.payload)) {
            return state;
        }
        const result = event.payload.result;
        if (!Array.isArray(result)) {
            throw new Error('workItemCommentsListOp: expected comment array');
        }
        return { ...state, items: result };
    },
});

export const workItemCreateForm = createForm({
    name: 'worktracker/work_item_create_form',
    schema: {
        title: { required: true, minLength: 1, maxLength: 255, errorKey: 'form.title_required' },
        description: {},
        board_id: {},
        priority: {},
    },
    initial: { title: '', description: '', board_id: '', priority: 'normal' },
    submitEvent: workItemsResource.events.CREATE_REQUESTED,
    buildPayload: (draft) => {
        const payload = {
            title: typeof draft.title === 'string' ? draft.title.trim() : '',
            description: typeof draft.description === 'string' ? draft.description : '',
            priority: typeof draft.priority === 'string' && draft.priority ? draft.priority : 'normal',
        };
        if (typeof draft.board_id === 'string' && draft.board_id.length > 0) {
            payload.board_id = draft.board_id;
        }
        return payload;
    },
});
