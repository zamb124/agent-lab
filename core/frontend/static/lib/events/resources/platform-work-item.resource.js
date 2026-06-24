/**
 * Платформенные фабрики WorkItem для cross-service badge/preview и счётчика задач.
 */

import { createAsyncOp } from '../index.js';
import { httpRequest } from '../http.js';
import { CoreEvents } from '../contract.js';

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
        return {
            ...state,
            assigned_open_count: assignedOpenCount,
            queue_inbox_count: queueInboxCount,
            total_open_count: assignedOpenCount + queueInboxCount,
        };
    },
});

export const platformWorkItemFactories = [
    platformWorkItemGetOp,
    platformWorkItemCountsOp,
];

export function createPlatformWorkItemCountsAuthEffect() {
    return (event, ctx) => {
        if (event.type === CoreEvents.AUTH_USER_LOADED) {
            platformWorkItemCountsOp.run({}, ctx);
        }
    };
}
