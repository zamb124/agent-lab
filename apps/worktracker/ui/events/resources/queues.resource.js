/**
 * Work queues — очереди задач (операторские и общие).
 */

import {
    createResourceCollection,
    createAsyncOp,
} from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const workQueuesResource = createResourceCollection({
    name: 'worktracker/work_queues',
    baseUrl: '/worktracker/api/v1/work-queues',
    idField: 'work_queue_id',
    operations: ['list', 'create'],
    transport: 'http',
    toastKeys: {
        create: 'worktracker:toast.queue_created',
        create_error: 'worktracker:toast.queue_create_failed',
    },
});

export const workQueueMembersListOp = createAsyncOp({
    name: 'worktracker/work_queue_members_list',
    silent: true,
    restMirror: { method: 'GET', path: '/worktracker/api/v1/work-queues/:work_queue_id/members' },
    extraInitial: { items: [] },
    request: async ({ payload }) => {
        if (!payload || typeof payload.work_queue_id !== 'string') {
            throw new Error('workQueueMembersListOp: payload.work_queue_id required');
        }
        return await httpRequest({
            method: 'GET',
            url: `/worktracker/api/v1/work-queues/${encodeURIComponent(payload.work_queue_id)}/members`,
        });
    },
    extraReducer: (state, event, events) => {
        if (event.type !== events.SUCCEEDED || !event.payload || !('result' in event.payload)) {
            return state;
        }
        const result = event.payload.result;
        if (!Array.isArray(result)) {
            throw new Error('workQueueMembersListOp: expected member array');
        }
        return { ...state, items: result };
    },
});

export const workQueueMemberAddOp = createAsyncOp({
    name: 'worktracker/work_queue_member_add',
    successToastKey: 'worktracker:toast.queue_member_added',
    errorToastKey: 'worktracker:toast.queue_member_add_failed',
    restMirror: { method: 'POST', path: '/worktracker/api/v1/work-queues/:work_queue_id/members' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.work_queue_id !== 'string') {
            throw new Error('workQueueMemberAddOp: payload.work_queue_id required');
        }
        if (!payload.member || typeof payload.member !== 'object') {
            throw new Error('workQueueMemberAddOp: payload.member required');
        }
        const body = {
            member: payload.member,
            role: typeof payload.role === 'string' ? payload.role : 'member',
        };
        return await httpRequest({
            method: 'POST',
            url: `/worktracker/api/v1/work-queues/${encodeURIComponent(payload.work_queue_id)}/members`,
            body,
        });
    },
});

export const workQueueMemberRemoveOp = createAsyncOp({
    name: 'worktracker/work_queue_member_remove',
    successToastKey: 'worktracker:toast.queue_member_removed',
    errorToastKey: 'worktracker:toast.queue_member_remove_failed',
    restMirror: { method: 'POST', path: '/worktracker/api/v1/work-queues/:work_queue_id/members/remove' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.work_queue_id !== 'string') {
            throw new Error('workQueueMemberRemoveOp: payload.work_queue_id required');
        }
        if (!payload.member || typeof payload.member !== 'object') {
            throw new Error('workQueueMemberRemoveOp: payload.member required');
        }
        return await httpRequest({
            method: 'POST',
            url: `/worktracker/api/v1/work-queues/${encodeURIComponent(payload.work_queue_id)}/members/remove`,
            body: { member: payload.member },
        });
    },
});
