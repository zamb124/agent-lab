/**
 * Платформенные фабрики WorkItem для cross-service badge/preview, list и мутаций.
 */

import { createAsyncOp, createResourceCollection } from '../index.js';
import { httpRequest } from '../http.js';
import { CoreEvents } from '../contract.js';

const WORK_ITEM_PUSH_EVENTS = Object.freeze([
    'worktracker/work_item/created',
    'worktracker/work_item/updated',
    'worktracker/work_item/moved',
    'worktracker/work_item/completed',
]);

function _mergeWorkItem(state, item) {
    const id = item.work_item_id;
    const idx = state.items.findIndex((x) => x && x.work_item_id === id);
    const items = idx === -1 ? [...state.items, item] : state.items.map((x, i) => (i === idx ? item : x));
    return { ...state, items, byId: { ...state.byId, [id]: item } };
}

export const platformWorkItemGetOp = createAsyncOp({
    name: 'platform/work_item_get',
    silent: true,
    restMirror: { method: 'GET', path: '/worktracker/api/v1/work-items/:work_item_id' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.work_item_id !== 'string' || payload.work_item_id.length === 0) {
            throw new Error('platformWorkItemGetOp: payload.work_item_id required');
        }
        return await httpRequest({
            method: 'GET',
            url: `/worktracker/api/v1/work-items/${encodeURIComponent(payload.work_item_id)}`,
        });
    },
});

export const platformWorkItemCountsOp = createAsyncOp({
    name: 'platform/work_item_counts',
    silent: true,
    restMirror: { method: 'GET', path: '/worktracker/api/v1/work-items/mine/summary' },
    extraInitial: {
        assigned_open_count: 0,
        queue_inbox_count: 0,
        total_open_count: 0,
        work_queue_ids: [],
    },
    request: async () => {
        return await httpRequest({
            method: 'GET',
            url: '/worktracker/api/v1/work-items/mine/summary',
        });
    },
    extraReducer: (state, event, events) => {
        if (event.type !== events.SUCCEEDED || !event.payload || !('result' in event.payload)) {
            return state;
        }
        const result = event.payload.result;
        if (!result || typeof result !== 'object') {
            return state;
        }
        const assignedOpenCount = typeof result.assigned_open_count === 'number' ? result.assigned_open_count : 0;
        const queueInboxCount = typeof result.queue_inbox_count === 'number' ? result.queue_inbox_count : 0;
        const workQueueIds = Array.isArray(result.work_queue_ids)
            ? result.work_queue_ids.filter((id) => typeof id === 'string' && id.length > 0)
            : [];
        return {
            ...state,
            assigned_open_count: assignedOpenCount,
            queue_inbox_count: queueInboxCount,
            total_open_count: assignedOpenCount + queueInboxCount,
            work_queue_ids: workQueueIds,
        };
    },
});

export const platformWorkItemsResource = createResourceCollection({
    name: 'platform/work_items',
    baseUrl: '/worktracker/api/v1/work-items',
    idField: 'work_item_id',
    operations: ['list', 'get', 'update'],
    transport: 'http',
    silent: true,
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
        query.limit = typeof payload.limit === 'number' ? payload.limit : 100;
        query.offset = typeof payload.offset === 'number' ? payload.offset : 0;
        return query;
    },
    toastKeys: {
        update: 'platform:work_item.update_success',
        update_error: 'platform:work_item.update_error',
    },
    extraReducer: (state, event) => {
        if (!WORK_ITEM_PUSH_EVENTS.includes(event.type)) {
            return state;
        }
        const payload = event.payload;
        if (!payload || typeof payload !== 'object') {
            return state;
        }
        const item = payload.work_item;
        if (!item || typeof item !== 'object' || typeof item.work_item_id !== 'string') {
            return state;
        }
        return _mergeWorkItem(state, item);
    },
    extraEffect: async (event, ctx, events) => {
        if (event.type !== 'flows/hitl_conversation/turn_appended') {
            return false;
        }
        const payload = event.payload;
        if (!payload || typeof payload !== 'object') {
            return true;
        }
        const workItemId = typeof payload.work_item_id === 'string' ? payload.work_item_id : '';
        if (workItemId.length === 0) {
            return true;
        }
        ctx.dispatch(
            events.ITEM_REQUESTED,
            { work_item_id: workItemId },
            { causation_id: event.id, source: 'ws' },
        );
        return true;
    },
});

export const platformWorkItemMoveOp = createAsyncOp({
    name: 'platform/work_item_move',
    silent: true,
    restMirror: { method: 'POST', path: '/worktracker/api/v1/work-items/:work_item_id/move' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.work_item_id !== 'string') {
            throw new Error('platformWorkItemMoveOp: payload.work_item_id required');
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

export const platformWorkItemAssignOp = createAsyncOp({
    name: 'platform/work_item_assign',
    successToastKey: 'platform:work_item.assign_success',
    errorToastKey: 'platform:work_item.assign_error',
    restMirror: { method: 'POST', path: '/worktracker/api/v1/work-items/:work_item_id/assign' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.work_item_id !== 'string') {
            throw new Error('platformWorkItemAssignOp: payload.work_item_id required');
        }
        if (!payload.assignment || typeof payload.assignment !== 'object') {
            throw new Error('platformWorkItemAssignOp: payload.assignment required');
        }
        return await httpRequest({
            method: 'POST',
            url: `/worktracker/api/v1/work-items/${encodeURIComponent(payload.work_item_id)}/assign`,
            body: { assignment: payload.assignment },
        });
    },
});

export const platformWorkItemFactories = [
    platformWorkItemGetOp,
    platformWorkItemCountsOp,
    platformWorkItemsResource,
    platformWorkItemMoveOp,
    platformWorkItemAssignOp,
];

export function createPlatformWorkItemCountsAuthEffect() {
    return (event, ctx) => {
        if (event.type === CoreEvents.AUTH_USER_LOADED) {
            platformWorkItemCountsOp.run({}, ctx);
        }
    };
}
